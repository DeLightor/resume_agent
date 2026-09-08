# Design: agent-write-guard

## 1. 目标与非目标

**目标**
1. Agent 发起的简历写入必须经用户明确同意才落库（结构性保证，非 prompt 约束）。
2. 复用既有 `ask_user` 暂停/恢复状态机，不新增会话状态。
3. 确认状态持久化，SSE 断线 / 刷新 / 切换会话后可恢复。
4. 被拒绝时用户反馈无损回传 LLM，Agent 可修改后重新发起（自然形成
   「提案 → 反馈 → 修改 → 再提案」循环，每轮都需用户交互，无死循环风险）。

**非目标**
- diff 逐字段接受/拒绝（US-32 编辑保护三件套范围，本变更只做整份确认）。
- Reviewer 双审（US-30，将在同一门禁点前叠加）。
- 「信任模式」跳过门禁（PRD 提及，v2.0 后续迭代）。

## 2. 状态机与数据流

复用 `awaiting_user` 状态；`pending_write` 与 `pending_question` 并列：

```text
LLM 调 write_node(node_id, content)          参数非法 → 走原有错误 tool result
        │ 参数合法
        ▼
session.pending_write = {tool_call_id, node_id, content}
session.status = awaiting_user; pending_question = 引导文案
emit write_confirm {node_id, content, question} → emit done(awaiting_user)
        │ 用户回复（resume 路径）
        ▼
is_write_confirmation(reply)?
        │ 是                                    │ 否（安全默认：不写）
        ▼                                        ▼
save_node_content(node_id, content)      （不执行写入）
tool result: {"ok": true, "written": true,   tool result: {"ok": false, "written": false,
             "node_id": ...}                              "user_reply": <全文>}
        └────────────┬───────────────────────────┘
                     ▼
        append tool message（tool_call_id 闭合 write_node 调用）
        记一条 write_node trace（round=0，恢复阶段解决）
        清空 pending_write → 进入 _loop 继续
```

### 2.1 消息序列合法性

write_node 与 ask_user 同为「暂停型调用」：assistant 消息含未闭合
tool_call 期间会话暂停，恢复时以 role=tool 消息闭合。
同一 assistant 消息内 write_node **之后**的其他 tool_calls 会被丢弃
（与 ask_user 现状一致，LLM 实际行为几乎总是单独调用，接受此限制）。

### 2.2 与 ask_user 恢复路径的关系

`resume()` 先查 `session.pending_write`：
- 存在 → 按 write 仲裁闭合对应的 write_node tool_call；
- 不存在 → 走既有 `_find_unclosed_ask_user` 路径。

两条路径互斥（一次只有一个未闭合的暂停型调用）。

## 3. 确认词表（安全默认）

`is_write_confirmation(reply: str) -> bool`（runner.py 模块级纯函数）：

规范化：去首尾空白 → 去末尾中英文标点（。！？，,.!?~～）→ 去语气词
（吧/呢/啊/呀/了）→ lowercase。

整句命中词表才确认：
`确认 / 确定写入 / 确认写入 / 同意 / 同意写入 / 写入 / 执行 / 可以 / 好 / 好的 /
没问题 / 行 / 嗯 / ok / okay / yes / y`

设计原则：**误判方向必须安全**——
- 假阴性（用户本意同意但被判为拒绝）：无害，LLM 看到回复原文会再次
  发起或说明；
- 假阳性（用户本意拒绝但被判为同意）：危险，因此自由文本一律不匹配。

## 4. 持久化

```sql
-- schema.sql（agent_sessions 新列，幂等迁移对齐 _migrate_upstream_columns 模式）
ALTER TABLE agent_sessions ADD COLUMN pending_write_json TEXT;
```

`AgentSession.pending_write: dict | None`（`{tool_call_id, node_id, content}`），
`save_session` / `_row_to_session` 序列化往返。
会话详情端点（`GET /api/agent/sessions/{id}`）返回 `pending_write`，
前端 `selectSession` / 断线 `recover` 时恢复确认卡片。

## 5. 事件协议

```json
{"type": "write_confirm", "node_id": "master",
 "content": {"experience": [], ...}, "question": "引导文案"}
```

- SSE event 帧名 = `write_confirm`；随后照旧发 `done(status=awaiting_user)`。
- 前端 `AgentEvent` 联合类型加该成员；时间线渲染为「请求写入节点」条目
  （内容预览可折叠 JsonBlock）；`pendingWrite` 存在且非 streaming 时底部
  渲染确认卡片（替代 ask_user 卡片）：内容预览 + [确认写入]（发送
  「确认」）+ [暂不写入]（发送「取消」）+ 自由输入框（发送修改意见）。

## 6. Prompt 约定

- `AGENT_SYSTEM_PROMPT` 增补：「修改简历通过 write_node 发起，系统会暂停
  等待用户确认，用户同意后才写入；被拒绝时根据用户反馈调整后可再次发起。」
- `write_node` 工具 description 同步说明确认语义。

## 7. 测试策略

- **runner 单元**（脚本化 LLM，真实 SQLite）：
  1. 合法 write_node → awaiting_user + pending_write 持久化 + 节点未被写；
  2. resume「确认」→ 节点已写 + tool result written:true + trace 记录；
  3. resume 自由文本 → 未写 + user_reply 回传 + LLM 继续；
  4. 非法参数 write_node → 不触发门禁，错误 tool result 原路返回；
  5. 确认词表纯函数表驱动测试（安全默认方向）；
  6. 写入后又发 write_node（新提案）正常再次门禁。
- **store 单元**：pending_write 序列化往返 / 清空。
- **API 契约**：会话详情含 pending_write；SSE 事件流含 write_confirm 帧。
- **前端**：tsc + build 零错误；浏览器冒烟走真实确认流。

## 8. 已知限制

- 同一 assistant 消息中 write_node 之后的 tool_calls 丢弃（同 ask_user 现状）。
- 词表确认依赖整句匹配，极短回复（单字「好」）判为确认——符合中文习惯。
- 门禁为会话级常开，无「信任模式」（后续迭代）。
