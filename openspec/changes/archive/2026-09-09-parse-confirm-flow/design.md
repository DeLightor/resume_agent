# Design: parse-confirm-flow

## 1. 状态机与数据流

```
upload（不变） → upload_records(parse_status=pending)
     │
     ▼ POST /api/resumes/parse
创建 parse_tasks(status=extracting)，后台 asyncio task 启动，立即返回 task_id
     │
     ▼ 后台任务（SSE 推送进度）
1. 文件解析：MinerU（asyncio.to_thread 包装同步轮询）
   ├─ 成功 → 事件 file_parsed {parser_used: "mineru", degraded: false}
   └─ MinerUError → 本地解析器 → 事件 file_parsed {parser_used: "local", degraded: true}
2. LLM 结构化提取（ResumeExtractor.extract，不变）
   → 事件 extracting
3. 置信度计算（parsers/confidence.py，纯函数）
4. 知识库个人信息提取（不覆盖，并存）
5. parse_tasks: status=awaiting_confirm, result_json 落库
   → 事件 done；upload_records.parse_status 保持 parsing
     │
     ▼ 前端拉取任务详情 → ParseConfirmModal（用户审阅/修正）
     │
     ▼ POST .../confirm {structured_resume, apply_knowledge_personal_info}
1. 按 apply_knowledge_personal_info 决定是否用知识库个人信息覆盖
2. TreeBuilder.build_from_resume 建版本树节点
3. _index_resume_to_knowledge(confirmed_text) 将最终确认数据写 knowledge_chunks + Chroma   ← 时序后移
4. parse_tasks: status=confirmed；upload_records.parse_status=success
     │
     ▼ 返回 {structured_resume, tree_node, deduplicated}（与旧 parse 成功响应同形状）
```

失败路径：任一步异常 → parse_tasks(status=failed, error=...) + SSE `error` 事件；
upload_records.parse_status=needs_review（沿用现有语义）。

## 2. 置信度算法（parsers/confidence.py）

确定性源文本回查，不用 LLM 自报（自报置信度不可验证，与诚实性原则冲突）。

- 归一化：NFKC + 转小写 + 去空白与常见标点（`-_—–·、，。：:;；()（）`）。
- 叶子字段（basic.*、education[i].* 等）：
  - 非空且归一化后是 raw_text 子串 → `high`；
  - 非空但未命中 → `low`；
  - 空/None → `low`（缺失）。
- 列表条目（experience[i]、projects[i]、education[i]）：条目级置信度 = 关键字段
  的聚合——experience 以 company+role 为关键字段，projects 以 name，
  education 以 school：全部命中 → `high`，部分命中 → `medium`，全未命中 → `low`。
- 输出形状：`{section: {field_or_index: level}}`，如
  `{"basic": {"phone": "high"}, "experience": {"0": "medium"}}`；
  列表条目内部字段置信度并入条目级（UI 只到条目/叶子两级，避免过载）。

## 3. API 契约

沿用统一 envelope（`api/response.py` success/error）。

### POST /api/resumes/parse（语义变更）
- 请求：`{upload_id}`（不变）
- 响应 data：`{task_id, status: "extracting"}`
- 重复调用：同 upload_id 存在 extracting/awaiting_confirm 任务时返回既有 task_id（幂等）。

### GET /api/resumes/parse/tasks/{task_id}/events（SSE，新增）
- `text/event-stream`，事件 `data:` 为 JSON，形如 `{"type": ..., ...}`：
  - `status` `{task_id, status}`
  - `file_parsed` `{parser_used: "mineru"|"local", degraded: bool}`
  - `extracting` `{}`（LLM 提取开始）
  - `done` `{task_id}`（提示前端拉详情）
  - `error` `{message}`
- 连接建立时若任务已终态（awaiting_confirm/failed/confirmed），立即补发
  `done`/`error` 后关闭——保证「SSE 连上之前任务已完成」的窗口不丢事件。

### GET /api/resumes/parse/tasks/{task_id}（轮询兜底，新增）
- data：`{task_id, upload_id, status, parser_used, degraded, structured_resume,
  confidence, knowledge_personal_info, error}`

### POST /api/resumes/parse/tasks/{task_id}/confirm（新增）
- 请求：`{structured_resume: object, apply_knowledge_personal_info: bool}`
- 服务端以 `StructuredResume.model_validate` 重校验用户提交数据（不信任客户端原样落库）。
- 响应 data：`{upload_id, structured_resume, tree_node, deduplicated}`（旧形状）。

### 数据库
```sql
CREATE TABLE IF NOT EXISTS parse_tasks (
    id              TEXT PRIMARY KEY,
    upload_id       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'extracting'
                    CHECK (status IN ('extracting', 'awaiting_confirm', 'confirmed', 'failed')),
    raw_text        TEXT,
    parser_used     TEXT,
    degraded        INTEGER NOT NULL DEFAULT 0,
    result_json     TEXT,   -- {structured_resume, confidence}
    knowledge_personal_json TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (upload_id) REFERENCES upload_records(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_parse_tasks_upload ON parse_tasks(upload_id);
```
`upload_records` 表无变更（parse_status 语义：parsing=提取中/待确认，success=已确认入库）。

## 4. 后台任务与 SSE 实现

- 提取任务用 `asyncio.create_task`（进程内，单用户本地应用的既有边界，不引任务队列）；
  任务句柄存模块级 dict `{task_id: asyncio.Task}`，SSE 端点直接订阅其事件队列
  （`asyncio.Queue`）+ 兜底读 parse_tasks 表终态，双保险避免丢事件。
- MinerU 同步客户端（requests）经 `asyncio.to_thread` 调用，不阻塞事件循环；
  内部轮询参数不变（2s/120s）。
- 服务重启丢内存任务：GET 详情读表，extracting 状态但无对应内存任务 → 视为
  failed（「服务重启导致任务中断，请重新解析」），前端可重新发起。

## 5. 前端

- `types/resume.ts`：`ParseTaskEvent`、`ParseTaskDetail`、`ConfidenceMap`、`ConfirmParseRequest`；
  `ParseResponse` 保留（confirm 响应复用）。
- `lib/api.ts`：`startParseResume(uploadId)`、`streamParseTaskEvents(taskId, onEvent, signal)`
  （复用 agent SSE 的 fetch-ReadableStream 解析模式）、`getParseTask(taskId)`、
  `confirmParse(taskId, body)`。
- `UploadZone.tsx`（简历模式）：状态机 `idle → uploading → parsing(SSE 进度文案) →
  confirming(打开 ParseConfirmModal) → success/error`；`parseFn` 注入点保留但
  简历模式默认走新流程；知识库模式（parseFn=null）不受影响。
- `ParseConfirmModal.tsx`（新）：分区表单（basic 联系方式栅格 / education、experience、
  projects 条目卡片可增删改 / skills 标签编辑）；每字段/条目置信度徽标
  （高=灰、中=琥珀、低=红），低置信度字段红色描边高亮；顶部 MinerU 降级横幅
  （degraded=true 时「云端解析不可用，已使用本地解析器，复杂排版可能识别不全」）；
  知识库个人信息与提取结果冲突时逐字段展示「知识库值 → 是否覆盖」勾选。
- 交互原则：确认前不产生任何写副作用（无树节点、无知识库写入）；关闭弹窗 =
  放弃本次解析（任务停留 awaiting_confirm，可从上传记录重新进入，不做自动清理）。

## 6. 测试策略（TDD）

- `parsers/confidence.py` 纯函数单测：high/medium/low 三档、归一化边界
  （全角/标点/空白）、空字段。
- `test_api.py`（resumes 部分）改两阶段：
  - POST /parse 返回 task_id 且不再直接建树（resume_versions 无新节点）；
  - GET 详情含 confidence 与 knowledge_personal_info；
  - confirm 后树节点存在、knowledge_chunks 有记录（确认前无——污染时序断言）；
  - apply_knowledge_personal_info=true/false 两种覆盖行为；
  - 幂等：重复 POST 返回同 task_id。
- SSE：事件生成器单测（mock LLM/MinerU），断言事件序列与终态补发。
- MinerU 降级：mock MinerUClient 抛 MinerUError → parser_used=local、degraded=1。
- 前端：`pnpm build`（tsc）+ 既有 lint；ParseConfirmModal 以类型与构建验证为主
  （项目无前端单测基建，不为此新增——遵循项目现状，UI 交给 QA 浏览器验证）。

## 7. 风险

| 风险 | 缓解 |
|------|------|
| 后台任务引用丢失被 GC / 重启丢任务 | 句柄存模块级 dict；详情端点对孤儿 extracting 任务判 failed |
| SSE 在任务已完成后来不及连 | 终态补发事件 + 轮询详情兜底 |
| confirm 提交被篡改的数据 | 服务端 StructuredResume 重校验 |
| 旧前端调用新 parse | 前后端同 commit 发布；本地单用户应用无版本漂移问题 |
| raw_text 大文本存 parse_tasks 膨胀 | 确认/失败后保留（30 天内可重确认），SQLite 单机量级可控；不引入清理定时器（v2.0 无此需求，留 tasks 备注观察） |

## 8. 接手工程评审（2026-09-09）

风险：高（增量数据库表、API 契约和入库状态机）。沿用现有功能分支与已确定范围。

- 架构：维持现有后台线程，阻塞 MinerU/LLM 不占请求事件循环；不引入队列或依赖。
  修正原设计 asyncio task 与实际线程的偏差。任务完成自行释放注册项；SSE 只观察，
  客户端断开不能改变任务生命周期。孤儿任务持久化 failed，重新 parse 可以重试。
- 数据：PRD 要求错误数据不进 RAG，因此索引内容必须是最终确认值序列化，原始文本
  仅留 parse_tasks 作回查。知识库写入异常必须向用户提示，不能静默宣称完全成功。
- 置信度：保留条目聚合并增加叶子路径（如 experience["0.period"]、
  experience["0.highlights.0"]）；日期、描述和成果也可回查、编辑。归一化为空不能命中。
- UX：原生 dialog + 分区字段表单；键盘焦点/关闭/提交中防重复；知识库值逐字段
  显示并由用户采用到可见草稿，提交 apply_knowledge_personal_info=false，避免第二次覆盖。
  关闭保留本次草稿并提供继续确认；localStorage 仅保存任务 ID，刷新后取服务端结果，
  未提交草稿不跨刷新保存。上传失败/任务失败/断网均提供明确重试。
- 测试：后端 pytest 补慢 SSE、孤儿重试、修正数据入库、叶子置信度回归；前端现状
  无组件测试基础设施，遵循第 6 节，以 tsc 红绿检查加真实浏览器交互 QA，不增加依赖。
  覆盖上传→待确认无节点→修正→确认建树、关闭恢复、SSE 失败轮询、知识库覆盖、移动端。
- 性能：SSE 使用低频数据库终态兜底；前端轮询与流均在完成/卸载时终止。单进程
  本地应用边界不变，多 worker 持久任务队列与定时清理不纳入本次。

以上为修复既定 US-31 验收缺口，不扩展产品范围。人工验收前不归档/提交/合并。

## 9. 人工验收追加范围（2026-09-09）

HJ 批准并验收：取消未确认上传、已确认简历列表、删除简历来源、方向展示、自定义方向。
新增 DELETE /resumes/parse/tasks/{task_id} 与 DELETE /resumes/uploads/{upload_id}。
删除来源不删除版本树节点；按 metadata_json.upload_id 清理知识切片。
确认请求增加可选 custom_direction；非空值去首尾空格、最多 80 字符后赋值，
LLM 提取的原有受限方向模型保留。upload_records.direction 保存最终方向，启动时增量添加。
树节点按方向复用，不是文件内容哈希去重；再次导入同方向会更新该方向节点内容。
实际代码将确认数据写入 knowledge_chunks 集合；此前对话称 resume_chunks 不准确。
已知实现边界见 tasks.md，未把验收未覆盖的异常场景标记为已修复。
