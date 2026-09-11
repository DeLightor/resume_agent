# US-35 Agent 长期记忆 (Agent Long-Term Memory)

## Why
目前简历 Agent（`AgentRunner` 与 `ReviewerAgent`）在单次会话或跨会话运行时缺乏对用户长期偏好、历史纠偏和风格习惯的持久化记忆：
1. 用户在一次对话中强调的偏好（如「以后所有经历都必须量化数据」、「技术栈不要写精通只写熟悉」、「偏好使用 STAR 原则描述」），在新建会话或下次使用时丢失，需要用户反复重申。
2. Reviewer 审查时缺乏个性化标准注入，无法按用户专属的风格偏好做红线检测。
3. 用户缺乏对 Agent 记忆的可见性和掌控权（无法查看、编辑、禁用或删除 Agent 记住的偏好）。

## What Changes
1. **持久化存储（Database Layer）**：
   - 在 SQLite 中新增 `agent_memories` 表，记录记忆项的唯一 ID、分类（`preference` 偏好、`correction` 纠偏、`style_sample` 风格习惯）、内容、来源、生效状态（`active`）与时间戳。
2. **记忆抽取与沉淀（Extraction）**：
   - 当用户在对话中表达显式指令（如「以后都...」、「请记住...」、「不要再...」）或提供风格纠偏时，系统自动识别沉淀为结构化记忆规则；同时支持用户手动在面板录入。
3. **记忆动态注入（Prompt Injection）**：
   - 在 `AgentRunner` 系统提示词与 `ReviewerAgent` 审查提示词中动态挂载生效的记忆规则。
   - 设定严格的 Token 预算限制（Top-K ≤ 8，Token 预算 ≤ 400 tokens），保障模型推理速度与上下文开销，采用 Fail-open 容错保障。
4. **前端可视化记忆管理面板（Workbench UI）**：
   - 在 `AgentWorkbench` 侧边栏/顶部提供「🧠 记忆」抽屉面板。
   - 用户可清晰查看已沉淀的记忆、一键切换启用/禁用开关、手动编辑内容、删除无用记忆或手动新增偏好。

## Impact
- 影响范围：
  - 后端：`db/schema.sql`、`init_db.py`、新增 `agents/memory_store.py`、新增 API 路由 `/api/agent/memories`、修改 `agents/runner.py` 与 `agents/reviewer.py`。
  - 前端：新增 `components/agent/MemoryDrawer.tsx`、修改 `components/agent/AgentWorkbench.tsx`、新增 API client 方法。
- 兼容性：`agent_memories` 表通过 `CREATE TABLE IF NOT EXISTS` 创建，不破坏原有节点、版本或会话数据。

## Rollback
- 数据库表独立无外键破坏性，如果回滚仅需切除 API 路由与提示词拼接逻辑，数据表可安全保留或 drop。
