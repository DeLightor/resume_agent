# Proposal: agent-write-guard

## Why

US-27/29 落地后，Agent 调用 `write_node` 会**直接整段覆盖**用户简历节点
（`save_node_content`），无任何确认环节。PRD-v2.0 架构原则明确
「人始终在环上：写操作默认走 diff 门禁」（§4.1 设计原则 3），
HJ 也在 US-29 验收时确认此缺口需要护栏：方案确定后 Agent 不应直接改简历，
必须先征得用户同意。

本变更是 Human Gate 的短期完整版（Reviewer 双审在 US-30 叠加）。

## What Changes

- **write_node 门禁**：AgentRunner 拦截 `write_node` 调用（参数合法时），
  不再直接写入，而是：
  - 暂停会话（`awaiting_user`），把待写入内容（node_id + content）存入
    会话新字段 `pending_write`；
  - 发 `write_confirm` SSE 事件（含待写入内容），前端渲染「写入确认卡片」；
  - 用户明确同意后才真正执行写入，否则原样把用户回复交还 LLM 继续编排。
- **resume 仲裁**：`awaiting_user` 恢复时，若存在 `pending_write`，按
  安全默认仲裁——仅整句明确确认词（「确认/同意/好的/OK/…」）才写入；
  其余任何回复（含「取消」「先别写」）一律不写入，回复全文作为
  tool result 交给 LLM 处理。
- **持久化**：`agent_sessions` 新增 `pending_write_json` 列（幂等迁移），
  刷新/断线/切会话后确认状态可恢复。
- **trace**：写入最终执行/拒绝时记一条 `write_node` trace（含用户回复）。
- **system prompt 与工具描述**：向 LLM 说明确认语义（发起写入会等用户确认，
  被拒后可依据反馈修改重试）。
- **前端**：AI 助手时间线渲染 `write_confirm` 事件；底部确认卡片展示
  待写入内容预览 + [确认写入] / [暂不写入] 按钮 + 自由输入修改意见。

## Impact

- 后端：`agents/runner.py`（门禁 + 仲裁）、`agents/store.py`
  （pending_write 序列化）、`db/schema.sql` + `db/init_db.py`
  （新列 + 幂等迁移）、`tools/agent_tools.py`（write_node 描述）、
  `api/agent.py`（会话详情返回 pending_write）。
- 前端：`types/agent.ts`（write_confirm 事件 + pending_write 字段）、
  `useAgentChat.ts`（事件处理与恢复）、`AgentWorkbench.tsx`（确认卡片）。
- 兼容性：SSE 新增事件类型（前端 default 分支可兜底渲染）；既有 9 工具
  其余行为不变；`ask_user` 暂停/恢复机制复用不改动语义。
- 数据库：`agent_sessions` 加一列 `pending_write_json TEXT`（可空，幂等
  ALTER，老库无损升级）。

## 回滚方案

- 后端 revert 单 commit；新列可空且无其他读取方，回滚后残留数据无影响。
- 前端确认卡片为纯增量 UI，revert 即可。
