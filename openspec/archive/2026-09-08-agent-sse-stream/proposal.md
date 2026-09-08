# Proposal: agent-sse-stream

## Why

US-27 已落地 Agent Runtime（工具注册表 + AgentRunner + 会话 API），但
`POST /sessions/{id}/messages` 是阻塞式 JSON：用户发消息后只能转圈等待
（一次多轮工具调用常超 30s），看不到 Agent 在思考什么、调了哪些工具。
PRD-v2.0 US-28 要求把过程透明化：SSE 事件流 + 前端行为面板，
建立「边看边等」的信任体验。

## What Changes

- **Runner 事件钩子**：`AgentRunner.run/resume` 增加可选 `on_event` 回调，
  循环各阶段发出事件（thinking / tool_call / tool_result / ask_user /
  done / error）。不传回调时行为与现有阻塞端点完全一致（向后兼容）。
- **新端点 `POST /api/agent/chat`**：body `{session_id, message}`，返回
  `text/event-stream`。事件按 SSE 格式逐条推送。
- **断线会话不丢失**：Runner 在独立 asyncio task 中执行，客户端断开仅
  取消 SSE 读端，运行继续至终态并持久化；前端断线后 refetch 会话恢复视图。
- **前端 Agent 工作台**：新增导航视图「AI 助手」，含会话管理、聊天输入、
  行为时间线（工具调用可展开入参出参）、ask_user 问答卡片。
- 协议预留 `review` / `draft` 事件类型（US-30 Reviewer 落地时启用）。

## Impact

- 代码：`agents/runner.py`（事件钩子）、`api/agent.py`（新端点）、
  前端 `types/`、`lib/api.ts`、`hooks/`（新）、`components/agent/`（新）、
  `GlobalToolbar` / `CenterPanel` / `types/knowledge.ts`（导航接入）。
- 兼容性：既有 4 个 Agent 端点契约不变；`POST /sessions/{id}/messages`
  保留（测试与降级使用）。
- 无数据库变更（agent_sessions/agent_traces 已就绪）。

## 回滚方案

- 后端：新端点独立于既有端点，回滚 = 移除 `POST /api/agent/chat` 路由
  与 runner 的 on_event 参数（既有测试保证阻塞路径不回归）。
- 前端：导航 Tab 与 CenterPanel 分支为纯增量，revert 单 commit 即可。
- 数据：无 schema 变更，无回滚需求。
