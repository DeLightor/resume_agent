# Design: agent-sse-stream

对齐 PRD-v2.0 US-28（SSE 流式与 Agent 行为面板）。

## 1. 目标与非目标

**目标**
1. `POST /api/agent/chat` 返回 `text/event-stream`，事件类型：
   `thinking` / `tool_call` / `tool_result` / `review` / `draft` / `done` / `error`
   （`review`/`draft` 本期只定义协议，US-30 启用）+ 运行时必需的 `ask_user`。
2. 前端「AI 助手」工作台：时间线渲染每步动作，工具调用可展开入参出参。
3. 断线会话不丢失：Runner 后台执行，状态持久化收敛。

**非目标**
- LLM token 级流式（chat_raw stream=True）——US-28 验收为步骤级透明，
  token 级留待后续（PRD 未要求）。
- US-29 的上下文集成（当前节点/JD/Gap 注入对话）与对话历史 UI 精修。
- EventSource（GET）自动重连——POST SSE 用 fetch 流，重连 = refetch
  会话状态（见 §4）。

## 2. 事件协议

SSE 帧格式（UTF-8）：

```
event: tool_call
data: {"round":1,"tool_call_id":"tc_1","name":"retrieve_knowledge","arguments":{"query":"Python"}}

```

| type | 时机 | data 字段 |
|------|------|-----------|
| `thinking` | 每轮 LLM 调用前 | `round` |
| `tool_call` | 工具执行前 | `round`, `tool_call_id`, `name`, `arguments` |
| `tool_result` | 工具执行后 | `round`, `tool_call_id`, `name`, `result` |
| `ask_user` | ask_user 暂停 | `question` |
| `done` | 终态 done | `final_message`, `rounds_used` |
| `error` | 运行失败 | `message` |
| `review` | （预留 US-30） | — |
| `draft` | （预留 US-30） | — |

说明：
- `ask_user` 事件后流以 `done`（`status=awaiting_user` 附带
  `pending_question`）收尾，前端凭它渲染输入卡片。
- `thinking` 不含推理内容（chat_raw 非流式拿不到），仅标记轮次开始。

## 3. 后端设计

### 3.1 Runner 事件钩子（agents/runner.py）

```python
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]

async def run(self, session_id, user_message=None,
              on_event: EventCallback | None = None) -> AgentRunResult
async def resume(self, session_id, answer,
                  on_event: EventCallback | None = None) -> AgentRunResult
```

`_loop` 在各阶段 `await self._emit(on_event, {...})`（None 安全）。
阻塞端点不传 `on_event` → 零行为差异（既有测试为回归保障）。

### 3.2 SSE 端点（api/agent.py）

```
POST /api/agent/chat
body: {"session_id": str, "message": str(min_length=1)}
```

流程：
1. 校验：会话不存在 → 404 JSON envelope；message 空白 → INVALID_REQUEST
   envelope；LLM 未配置 → LLM_NOT_CONFIGURED envelope（错误仍在流开始前，
   返回普通 JSON 与既有端点一致）。
2. `asyncio.Queue` + 独立 `asyncio.create_task` 执行
   `runner.run/resume(..., on_event=queue.put_nowait)`；任务引用存入
   模块级 `_background_runs: set`（防 GC，完成即丢弃）。
3. `StreamingResponse(gen(), media_type="text/event-stream")`：
   generator 从 queue 取事件渲染 SSE 帧；收到终态事件（done/error）后
   排空队列并结束。
4. 客户端断开 → generator 被 FastAPI 取消，后台 task 不受影响，
   会话状态照常持久化收敛（「断线会话不丢失」的服务端保障）。
5. 心跳：queue 空转 15s 发 `: keepalive\n\n`（防代理空闲断连）。
6. 响应头 `X-Accel-Buffering: no` + `Cache-Control: no-cache`。

awaiting_user 状态下 POST chat → `runner.resume`（同既有 messages 端点
语义）。

### 3.3 与既有端点关系

`POST /sessions/{id}/messages` 保留：测试、非流式调用方、降级路径。
两个端点共享 Runner/store，无逻辑分叉。

## 4. 前端设计

### 4.1 类型与 API（无新依赖）

- `types/agent.ts`：`AgentEvent` 联合类型 + 会话摘要/详情类型。
- `lib/api.ts` 新增：`createAgentSession` / `listAgentSessions` /
  `getAgentSession`（REST）与 `streamAgentChat(sessionId, message,
  {onEvent, signal})`：`fetch` POST + `ReadableStream` 逐行解析
  `event:`/`data:` 帧（手写 SSE parser，不引第三方库）。

### 4.2 useAgentChat hook

- 状态：`sessions`（历史列表）、`activeSessionId`、`events`（当次运行
  事件累积）、`status`（idle/running/awaiting_user/done/failed）、
  `pendingQuestion`、`finalMessage`。
- `send(message)`：streamAgentChat 累积事件；`done` 后刷新会话列表。
- 断线恢复：`onerror` → 终止流 → `getAgentSession(activeSessionId)`
  轮询（2s）至非 running 终态 → 用会话 messages 重渲染结论；
  网络恢复事件（`window online`）触发同一路径。
- 刷新恢复：进入视图时拉会话列表，选中会话即恢复历史。

### 4.3 AgentWorkbench 组件（components/agent/）

中栏新视图（`ActiveView` 增加 `'agent'`，NAV_TABS 增加「AI 助手」，
CenterPanel 分支渲染），三区布局：

```
┌─────────────┬──────────────────────────┐
│ 会话列表     │ 行为时间线（滚动）         │
│ (新建/切换)  │  ● thinking 第1轮…        │
│             │  ● tool_call retrieve_…   │
│             │    ▸ 展开入参/出参         │
│             │  ● ask_user 问题卡片+输入   │
│             │  ● done 最终回答           │
│             ├──────────────────────────┤
│             │ [输入框] [发送]  (固定底部) │
└─────────────┴──────────────────────────┘
```

- 时间线条目：类型图标 + 标题 + 时间戳；tool_call/result 可展开
  （`<details>` 风格手风琴，入参出参 JSON 等宽渲染）。
- ask_user：问题卡片 + 输入框，提交走 `send()`（resume 路径）。
- 动画：条目依次淡入（200ms），hover 缓动（用户偏好较慢动效）。

## 5. 测试策略

**后端（TDD）**
1. Runner 事件序列：FakeLLM 脚本化
   `tool_calls → tool_calls → 终结`，断言事件序列
   `[thinking, tool_call, tool_result, thinking, tool_call, tool_result,
   thinking, done]`；ask_user 暂停序列；异常 → error 事件；轮次耗尽。
2. SSE 端点契约：TestClient/httpx stream 解析事件流（正常全流程 /
   awaiting_user / 404 / 空 message / LLM 未配置）；断线后台收敛
   （直接 task 语义验证）。
3. 既有 5 个 Agent 测试文件全绿（阻塞路径回归）。

**前端**
- 无测试框架（vitest 未配置，不加依赖），验证 = `tsc --noEmit` +
  `eslint` + `vite build` + HJ 手工冒烟。

## 6. 风险与决策记录

| 决策 | 理由 |
|------|------|
| 步骤级而非 token 级流式 | PRD 验收只要求步骤透明；token 级需改 LLM 客户端流式协议，收益/成本比低 |
| POST SSE + fetch 手写解析 | EventSource 仅支持 GET；不引第三方 SSE 库（工程约束：无批准不加依赖） |
| 断线 = 后台跑完 + refetch | 比「可重挂载的事件总线 + Last-Event-ID 重放」简单一个数量级；会话状态在 SQLite 天然满足「不丢失」 |
| 既有 messages 端点保留 | 测试与降级路径；避免破坏性契约变更 |
| ask_user 事件超出 PRD 事件清单 | 既有 Runtime 语义必需；US-29 验收（输入卡片）依赖它 |
