# Tasks: parse-confirm-flow

## 1. 规格与准备

- [x] 1.1 阅读现状代码（resumes.py / mineru_client.py / extractor.py / schema.sql / UploadZone.tsx / api.ts）
- [x] 1.2 proposal / design 落稿（契约变更、置信度算法、时序后移方案确定）

## 2. 后端（TDD）

- [x] 2.1 `parsers/confidence.py`：先写单测（high/medium/low、归一化边界、空字段）→ 实现 → 绿
- [x] 2.2 DB：schema.sql 新增 parse_tasks 表 + init_db.py TABLES 注册 + test_db 断言
- [x] 2.3 `POST /api/resumes/parse` 改异步启动（返回 task_id、幂等、后台任务骨架）
      ——先改 test_api.py 两阶段断言（红）→ 实现（绿）
- [x] 2.4 提取任务：文件解析（MinerU 后台线程 + 本地降级 + degraded 标记）→
      LLM 提取 → 置信度 → 知识库个人信息并存 → awaiting_confirm 落库
- [x] 2.5 SSE 端点 `GET /parse/tasks/{id}/events`：事件序列 + 终态补发（单测）
- [x] 2.6 详情端点 `GET /parse/tasks/{id}`（含孤儿 extracting 判 failed）
- [x] 2.7 confirm 端点：服务端重校验 + 覆盖开关 + 建树 + 知识库写入时序断言
- [x] 2.8 全量后端测试通过

## 3. 前端

- [x] 3.1 types/resume.ts + lib/api.ts：新类型与 4 个函数（startParse/streamEvents/getTask/confirm）
- [x] 3.2 UploadZone 状态机：parsing 阶段接 SSE 进度文案 → 完成后打开确认弹窗
- [x] 3.3 ParseConfirmModal：分区编辑 + 置信度徽标/高亮 + 降级横幅 + 覆盖选择 + 确认提交
- [x] 3.4 tsc + build 通过；新增后端文件 Ruff 通过（全仓历史 lint 问题另记）

## 4. 验证与交付

- [x] 4.1 openspec validate（如可用）+ 全量后端测试 + 前端构建
- [x] 4.2 交付 review（diff 级自查：契约、时序、边界）
- [x] 4.3 QA：代理确认首页可访问；HJ 完成真实上传→确认→建树及追加功能测试并反馈通过
- [x] 4.4 HJ 人工验收通过（2026-09-09），授权归档提交；合并/推送不在本次指令范围

## 5. 验收反馈后的追加功能

- [x] 5.1 未确认任务提供取消入口；取消上传记录、任务和原文件
- [x] 5.2 知识库页面显示已确认的上传记录
- [x] 5.3 已入库简历提供删除入口，保留版本树节点
- [x] 5.4 upload_records.direction 增量列与启动迁移，确认时保存方向
- [x] 5.5 确认界面输入 custom_direction，沿用方向节点创建逻辑
- [x] 5.6 自定义方向与来源删除回归测试；HJ 最终反馈“测试通过了”

## 验证与未覆盖边界

人工验收来源：当前任务中 HJ 两轮浏览器测试反馈。代理浏览器检查仅覆盖首页，
没有代理独立执行完整上传回归；不将 HJ 测试冒充代理 E2E。
本次归档提交保存已验收实现，不表示异常路径全部完成：
- “重新选择文件”目前只关闭弹窗，尚未自动取消并打开文件选择器。
- 删除来源时 Chroma 失败仍被忽略，可能残留向量；SQLite/向量库/文件不具备跨存储原子性。
- 简历列表沿用 upload_records 全量查询，尚未过滤知识素材；历史上传 direction 未回填。
- 确认使用知识库整体覆盖时会再次走旧方向校验，自定义方向可能回退；当前 UI 使用逐项采用。
- 单进程内存任务不支持多 worker；取消活动后台任务的竞态尚未完整覆盖。
这些限制保留在归档中，后续修复需专门回归验证，不声称已解决。

提交前验证（2026-09-09）：后端 pytest 402 passed / 6 个依赖弃用警告；
格式修正后 recovery + db 聚焦回归 31 项通过；make build（含 tsc -b）通过，
仅有 500 kB 包体积警告；本次 API/confidence/测试文件 Ruff 检查通过；
openspec validate parse-confirm-flow --strict 与 git diff --check 通过。
