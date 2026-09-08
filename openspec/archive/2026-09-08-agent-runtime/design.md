# Design: agent-runtime

> 关联 proposal.md | 技术栈以实际代码为准（FastAPI + SQLite + openai SDK / DeepSeek 协议，不引入 LangGraph）

## 1. 架构总览

```
api/agent.py (REST, 同步 JSON)
    │
    ▼
agents/runner.py ──── AgentRunner（多轮循环）
    │  持有 messages 历史（持久化到 agent_sessions）
    │  每轮: LLMClient.chat_raw(messages, tools)
    │  tool_calls → ToolRegistry.execute → trace 落库
    │  ask_user   → 暂停: status=awaiting_user, 持久化后中断
    ▼
agents/registry.py ── ToolRegistry
    │
    ▼
tools/*.py（9 个工具实现，薄封装现有能力）
```

## 2. 关键决策

### 2.1 Runtime 自持消息历史，不复用 `chat_with_tools`

`LLMClient.chat_with_tools`（llm/client.py#L115）是封闭循环：messages 是函数局部变量，无逐轮回调。而本变更需要：

- messages 持久化（ask_user 暂停后恢复、US-29 对话历史）
- 每轮工具调用写 trace
- 为 US-28 SSE 预留逐事件 hook 点

**决策**：给 `LLMClient` 新增最小方法 `chat_raw(messages, tools=None) -> ChatCompletionMessage`（单轮调用，返回原始 message），AgentRunner 用它逐轮驱动并自己持有 messages。既有 `chat` / `chat_with_tools` 零改动。

### 2.2 Tool 协议与 Registry

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]          # JSON Schema
    execute: Callable[[dict[str, Any]], Awaitable[Any]]

class ToolRegistry:
    def register(spec: ToolSpec) -> None
    def schemas() -> list[dict]          # 转 OpenAI tools 格式
    async def execute(name: str, args: dict) -> Any   # 未知工具/执行异常 → 返回 error 字符串（喂回 LLM，不中断循环）
```

- 工具执行失败不抛异常中断循环，而是把 `{"error": ...}` 作为 tool result 返回给 LLM（与 chat_with_tools 现有行为一致，LLM 有机会自救）
- `ask_user` 由 AgentRunner 特判（见 2.4），不走 registry.execute

### 2.3 工具清单与实现映射

| 工具名 | 输入 | 封装的现有实现 | 说明 |
|--------|------|----------------|------|
| `retrieve_knowledge` | query, top_k | generate.py `_search_knowledge_base` | 抽到 `services/knowledge_search.py`，generate.py 改为调用同一函数（消除复制） |
| `parse_jd` | jd_text | jd.py 结构化提取 LLM 逻辑 | 抽到 `services/jd_extract.py`；截图→文本的 MinerU 部分不在工具范围 |
| `analyze_gap` | structured_jd | gap_report.py 核心 | 抽到 `services/gap_analyzer.py` |
| `read_node` | node_id | tree.py `get_node` 内部逻辑 | 复用 `_row_to_node` |
| `write_node` | node_id, content | generate.py `_save_node_content` | 抽公共函数；乐观锁/commit 属 US-32 |
| `list_templates` | 无 | api/templates.py | PRD 中 render_preview 的后端等价物：预览渲染在前端，后端工具返回模板配置列表 |
| `export_pdf` | node_id, template_id | api/export.py + pdf_builder | 返回生成结果（文件名/成功标志） |
| `web_search` | query, max_results | tools/tavily_search.py `search_web` | 已存在，直接注册 |
| `ask_user` | question | 新增 | 特殊工具，Runner 特判 |

**PRD 偏差说明**：`render_preview` 调整为 `list_templates`。理由：简历预览渲染在前端（React），后端无渲染产物；Agent 需要"知道有哪些模板"的能力，`export_pdf` 覆盖产出需求。PRD-v2.0 后续修订时同步。

### 2.4 会话状态机与 ask_user

```
[创建] → running ──正常结束──→ done
            │ │
            │ └──LLM 调用 ask_user──→ awaiting_user
            │                            │ 用户 POST /messages (answer)
            │                            ▼
            └──────────────────────── running（继续循环）
        （任意状态异常 → failed）
```

- `agent_sessions.messages_json` 存完整 OpenAI 协议消息数组（含 tool_calls / tool results），恢复 = 直接续跑
- ask_user 暂停时：assistant 消息（含 tool_calls）与 `pending_question` 一并持久化；用户回答作为 tool result 追加后继续
- 单次 run 内 ask_user 不限次数，但受总轮数上限约束

### 2.5 AgentRunner 循环

```python
async def run(self, session) -> AgentResult:
    for round in range(settings.agent_max_rounds):     # 默认 8
        msg = await llm.chat_raw(session.messages, registry.schemas())
        session.messages.append(msg)
        if not msg.tool_calls:
            session.status = done; break
        for tc in msg.tool_calls:
            if tc.name == "ask_user":
                session.status = awaiting_user; session.pending_question = tc.args.question
                持久化; return AgentResult(paused=True)
            trace = await registry.execute(tc.name, tc.args)   # 写 agent_traces
            session.messages.append(tool_result)
    else:  # 轮次耗尽
        强制无 tools 最终响应（对齐 chat_with_tools 既有语义）
```

### 2.6 数据库

```sql
CREATE TABLE IF NOT EXISTS agent_sessions (
    id              TEXT PRIMARY KEY,           -- UUID v4
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'awaiting_user', 'done', 'failed')),
    context_json    TEXT,                       -- 会话上下文 {current_node_id, jd_summary, ...}
    messages_json   TEXT NOT NULL DEFAULT '[]', -- OpenAI 协议消息数组
    pending_question TEXT,                      -- awaiting_user 时的待答问题
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS agent_traces (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    round           INTEGER NOT NULL,           -- 第几轮
    tool_name       TEXT NOT NULL,
    input_json      TEXT,                       -- 参数
    output_json     TEXT,                       -- 结果（截断至 4KB 防 prompt 失控）
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE
);
```

沿用项目模式：schema.sql 追加 + `IF NOT EXISTS` 幂等，无独立 migration 机制。

### 2.7 API 契约

| 端点 | 方法 | 语义 |
|------|------|------|
| `/api/agent/sessions` | POST | 创建会话（可带 context）；返回 session |
| `/api/agent/sessions` | GET | 会话列表（id/status/时间，不含消息体） |
| `/api/agent/sessions/{id}` | GET | 会话详情（含 messages） |
| `/api/agent/sessions/{id}/messages` | POST | 发送用户消息并运行至终止（done / awaiting_user / failed / 轮次耗尽）；awaiting_user 时再次调用即恢复 |

同步阻塞版本；US-28 将 `/messages` 升级为 SSE 流式，契约字段向前兼容。

### 2.8 配置

`config.py` Settings 新增：`agent_max_rounds: int = 8`（环境变量 `AGENT_MAX_ROUNDS`）。

## 3. 测试策略

- **单元**：ToolRegistry（注册/schema 转换/未知工具错误返回）、每个工具（mock Chroma/LLM/DB 依赖，验证 schema 校验与输出裁剪）、AgentRunner（mock `chat_raw` 脚本化返回序列：正常终结 / 工具循环 / ask_user 暂停 / 轮次耗尽 / 工具异常不中断）
- **持久化**：session 状态机各迁移路径读写往返
- **API 契约**：TestClient + mock AgentRunner，端点 schema 与状态码
- **既有回归**：generate.py / jd.py / gap_report.py 改为调用抽取后的公共函数，既有测试必须保持绿（抽取是纯移动，不改逻辑）

## 4. 风险

| 风险 | 缓解 |
|------|------|
| DeepSeek function calling 多轮不稳定 | 轮数硬上限 + 超限强制无工具响应（对齐既有语义）+ trace 可回放调试 |
| messages_json 膨胀 | 工具输出截断 4KB；会话级上限（消息超长时 oldest tool results 摘要裁剪，v1 先不做，留观察） |
| ask_user 恢复时消息序列非法（缺 tool result） | 恢复路径强制校验最后一条 tool_call 已闭合，非法则 failed |
