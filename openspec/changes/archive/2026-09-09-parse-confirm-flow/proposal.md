# Proposal: parse-confirm-flow

## Why

PRD-v2.0 US-31（B2）解析确认流。现状 `/api/resumes/parse`（[resumes.py](../../../backend/src/resume_agent/api/resumes.py)）
是同步一条龙：文件解析 → LLM 结构化提取 → **静默**用知识库个人信息覆盖提取结果 →
直接写版本树节点 → raw_text 直接写知识库。PRD 诊断的结构性问题全部成立：

- 提取结果（年份、公司名）直接入树，无确认环节；错误数据还会被 RAG 检索放大；
- 无字段级置信度，用户不知道哪些字段可信；
- 个人信息覆盖逻辑对用户隐藏（电话/邮箱被静默替换）；
- MinerU 阻塞式轮询（2s 间隔 / 120s 超时）在请求线程里跑，前端全程转圈，超时即失败。

## What Changes

- **两阶段解析**：`POST /api/resumes/parse` 语义变更为「启动异步提取任务」，
  立即返回 `task_id`；新增 SSE 端点推送进度；新增确认端点，**确认后才建树 + 写知识库**。
  - `POST /api/resumes/parse` → `{task_id}`（异步启动，upload_records.parse_status 走 pending→parsing）
  - `GET /api/resumes/parse/tasks/{task_id}/events` → SSE（`status` / `file_parsed` / `extracting` / `done` / `error`）
  - `GET /api/resumes/parse/tasks/{task_id}` → 任务详情（轮询兜底）：结构化结果 + 置信度 + 知识库个人信息
  - `POST /api/resumes/parse/tasks/{task_id}/confirm` → 用户审阅修正后的最终数据入库
    （建版本树节点 + 最终确认数据分块写知识库 + parse_status=success）
- **字段置信度**（新模块 `parsers/confidence.py`）：基于**源文本回查**的确定性判定
  （归一化子串匹配），不用 LLM 自报——与项目「诚实性结构性保证」原则一致：
  - 高：字段值在简历原文中命中；
  - 中：列表条目部分关键字段命中（如经历只命中公司名未命中时间）；
  - 低：原文未命中或字段为空。确认界面低置信度字段高亮。
- **个人信息覆盖可见化**：提取阶段保留知识库个人信息提取（不覆盖），结果中并存
  `structured_resume`（LLM 从简历提取）与 `knowledge_personal_info`（知识库已有）；
  确认请求携带 `apply_knowledge_personal_info: bool`，由用户显式选择是否覆盖。
- **MinerU 异步 + 降级提示**：解析任务在后台 asyncio task 中执行（MinerU 同步轮询
  经 `asyncio.to_thread`），SSE 推送进度；MinerU 超时/失败自动降级本地解析器
  （沿用现有 fallback），结果与事件中携带 `parser_used`（mineru/local）与
  `degraded` 标记，前端展示降级提示。
- **知识库写入时序**：`_index_resume_to_knowledge` 从提取阶段迁移到确认阶段——
  用户确认（含修正）后最终数据才写入 knowledge_chunks/Chroma，错误数据不再污染 RAG。
- **前端确认界面**（新组件 `ParseConfirmModal`）：分区渲染结构化结果
  （basic/education/experience/projects/skills），字段级可编辑，置信度徽标 +
  低置信度高亮；知识库个人信息覆盖选择提示；MinerU 降级提示；确认后回调原
  `onFileUploaded` 流（tree_node 数据形状不变）。

## Impact

- 后端：`api/resumes.py`（parse 拆两阶段 + 3 个新端点）、`parsers/confidence.py`（新）、
  `db/schema.sql` + `init_db.py`（新表 `parse_tasks`）。
- 前端：`lib/api.ts`（新类型 + startParse/streamParseEvents/getParseTask/confirmParse）、
  `types/resume.ts`（ParseTask/ParseTaskEvent/ConfirmRequest）、
  `components/common/UploadZone.tsx`（状态机增加 confirming 阶段）、
  `components/common/ParseConfirmModal.tsx`（新）。
- 兼容性：`POST /api/resumes/parse` 响应结构变更（`{task_id}` 替代完整结果）——
  这是本规格批准的契约变更；唯一调用方为前端 UploadZone（同步改造）与后端测试。
  确认端点返回数据形状与旧 parse 成功响应一致（structured_resume/tree_node/deduplicated），
  下游（onFileUploaded 回调链）零改动。
- 测试：`test_api.py` / `test_parsers.py` 中旧 parse 同步断言改为两阶段流程；
  新增 confidence 单测、SSE 事件单测、知识库时序测试（确认前无 chunks、确认后有）。

## 回滚方案

- 后端 revert 单 commit（parse_tasks 表为增量新表，旧表无 schema 变更，无数据迁移）；
- 前端 revert UploadZone + 新组件；
- `parse_status` 枚举未扩展，无 CHECK 约束变更，回滚无残留风险。

## 验收追加范围与回滚补充

2026-09-09 HJ 批准取消上传、已确认来源列表及删除、方向展示与自定义方向，并反馈测试通过。
新增 upload_records.direction 列为 nullable，旧代码回滚可忽略该列，不执行 DROP。
来源删除是用户主动操作，删除后的原文件不能靠代码回滚恢复。
详见 design.md 第 9 节与 tasks.md 中的验证边界。
