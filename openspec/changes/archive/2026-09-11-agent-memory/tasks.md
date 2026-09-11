## 1. 规格和评审
- [x] 对照 PRD US-35 验收标准与当前代码，编写 proposal 与 design
- [x] 向 HJ 汇报设计方案并获得开工确认 (2026-09-11 获得授权)

## 2. 后端 TDD 与实现
- [x] 数据库更新：在 `schema.sql` 和 `init_db.py` 中添加 `agent_memories` 表结构（保留已有数据）
- [x] 存储层实现：编写 `backend/src/resume_agent/agents/memory_store.py`（CRUD、Top-K 获取、提示词注入格式化）
- [x] API 路由实现：添加 `backend/src/resume_agent/api/memory.py` 路由并注册至 `api/router.py`
- [x] 编写并执行单元测试：`backend/tests/test_agent_memory.py`，覆盖 CRUD、筛选、格式化、边界截断与容错（11 个测试全部通过）
- [x] Agent 提示词挂载与记忆提取：在 `runner.py` 与 `reviewer.py` 中动态挂载记忆，在 `AgentRunner` 中增加指令意图识别沉淀
- [x] 记忆工具封装与删除能力：在 `agent_tools.py` 中添加 `delete_memory` 与 `list_memories` 工具，支持按文字内容模糊检索、按最新记录删除，以及按 ID 删除
- [x] AgentRunner 与事件通知：更新 `AGENT_SYSTEM_PROMPT` 引导 AI 在用户要求删除记忆时使用工具，工具执行成功后推送 `memory_deleted` SSE 事件
- [x] 前端时间线联动：在 `AgentWorkbench.tsx` 中处理 `memory_deleted` 事件，实时刷新记忆角标与时间线显示

## 3. 前端界面实现
- [x] 前端类型与 API 封装：在 `frontend/src/types/agent.ts` 与 `frontend/src/lib/api.ts` 中增加记忆项接口定义与 CRUD 请求方法
- [x] 记忆抽屉组件：编写 `frontend/src/components/agent/MemoryDrawer.tsx`，支持列表展示、启用/禁用、编辑、删除与新增
- [x] 工作台集成：在 `frontend/src/components/agent/AgentWorkbench.tsx` 顶部工具栏挂载「🧠 记忆」入口与数量徽章，并在时间线中渲染 `memory_created` 事件

## 4. 自动化验证与质量检查
- [x] 执行后端单元测试与新工具测试（102 个测试全部通过）
- [x] 执行后端代码风格检查：`ruff check`（0 error）
- [x] 执行前端类型检查与构建：`pnpm run typecheck` & `pnpm run build`（全部通过）
- [x] 更新验证报告：`verification.md`

## 5. 人工验收与交付
- [x] 提供给 HJ 详细的手工验证操作步骤与测试指南
- [x] 等待 HJ 手工验收通过授权（2026-09-11 18:31 HJ 确认效果符合预期并授权归档合并）
- [x] 经授权后归档 OpenSpec 并执行 Git commit / merge / push

