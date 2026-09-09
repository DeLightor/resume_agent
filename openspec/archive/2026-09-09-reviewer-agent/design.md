# Design: reviewer-agent

## 1. 架构与模块边界

```text
AgentRunner._loop
  └─ LLM 调 write_node(node_id, content) 参数合法
        │
        ▼
  ReviewerAgent.review_draft(content, structured_jd, evidence)   ← 独立 LLM 调用
        │  （evidence = search_knowledge(草稿关键词, top_k=5)；
        │    structured_jd = session.context.structured_jd）
        ▼
  emit review {passed, round, node_id, issues, summary}
        │
   ┌────┴─────────────────────────────┐
   │ 不通过 且 本轮打回 < 2 次          │ 通过 或 已打回 2 次
   ▼                                  ▼
  tool result 闭合 write_node 调用：   进入 agent-write-guard 门禁：
  {ok: false, rejected_by_review,     pending_write 附 review 字段
   review: issues + 修改意见}          emit write_confirm（含 review）
  LLM 依据意见重写（同一 _loop 继续）    awaiting_user 等用户确认
```

- **独立上下文**：ReviewerAgent 每次审查新建 LLM 调用（system prompt +
  草稿/证据），不携带 Orchestrator 的 messages 历史——对草稿无「忠诚度」。
- **打回上限**：`_loop` 内局部计数 `write_review_rounds`，最多打回 2 次
  （共 3 次审查）；用户在门禁拒绝后 LLM 重新发起的写入属新一轮
  run/resume，计数自然归零。
- **fail-open**：LLM 未配置、审查 LLM 调用异常、JSON 解析失败 →
  `{passed: true, issues: [], summary: "审查跳过（原因）"}`，不阻塞写入。

## 2. ReviewerAgent 接口（agents/reviewer.py）

```python
REVIEW_ISSUE_TYPES = ("knowledge_boundary", "cliche", "jd_coverage",
                      "unverified_number", "other")

class ReviewerAgent:
    def __init__(self, llm: Any | None = None) -> None: ...

    async def review_draft(self, content: dict, structured_jd: dict | None,
                           evidence: list[dict]) -> dict:
        """审查待写入草稿。返回 {passed: bool, issues: [{type, message}], summary: str}"""

    async def review_evidence(self, evidence: list[dict]) -> dict:
        """审核知识库检索片段（迁移自 generate._run_reflection）。
        返回 {issues_found, issues, notes}，与旧实现形状兼容。"""
```

- `review_draft` prompt 要求输出 JSON：`{passed, issues: [{type, message}],
  summary}`；审查维度与 PRD 验收标准一一对应。
- `review_evidence` 沿用旧 `_REFLECTION_PROMPT` 语义（套话/矛盾/夸大），
  保留「LLM 未配置/异常 → 模板兜底」行为。

## 3. Runner 集成（agents/runner.py）

- `AgentRunner.__init__` 新增 `reviewer` 参数（默认 `ReviewerAgent()`，
  测试可注入 script mock）。
- 门禁点改造（`_loop` 中 `WRITE_NODE_TOOL_NAME and _is_gated_write` 分支）：
  1. 组装审查输入：`_review_query(content)` 从草稿提取文本关键词；
     `search_knowledge([query], top_k=5)` 取证据；`structured_jd` 取
     `session.context.get("structured_jd")`；
  2. `review = await self.reviewer.review_draft(...)`；emit `review` 事件
     （含 `round=write_review_rounds+1`）；
  3. 不通过且 `write_review_rounds < 2`：计数 +1，以 tool message 闭合该
     write_node 调用（content = `{ok: false, written: false,
     rejected_by_review: true, review: ...}`），记 trace，`continue`
     处理后续 tool_calls（LLM 下轮读到意见重写）；
  4. 否则进入原门禁流程：`pending_write` 增加 `review` 字段，
     `write_confirm` 事件与 done 事件不变，确认卡片可展示问题。
- system prompt 补充一条：写入被审查打回时，按审查意见修改内容后重新发起。

## 4. 事件协议（SSE，US-28 协议扩展）

```jsonc
// 新增：审查完成（每次审查发一条，打回与放行都发）
{ "type": "review", "node_id": "master", "round": 1,
  "passed": false,
  "issues": [{"type": "cliche", "message": "「负责优化系统性能」无量化结果"}],
  "summary": "发现 1 处套话，建议补充量化数据" }

// write_confirm 增加可选 review 字段（通过或打回耗尽后进入门禁时）
{ "type": "write_confirm", "node_id": "...", "content": {...},
  "question": "...", "review": {"passed": true, "issues": [], "summary": "..."} }
```

`pending_write`（会话详情）：`{tool_call_id, node_id, content, review?}`。

## 5. 反思迁移（api/generate.py）

- 删除 `_REFLECTION_PROMPT` 与 `_run_reflection`；
- 两处调用点改 `await ReviewerAgent().review_evidence(evidence)`；
- 响应字段 `reflection`（`{issues_found, issues, notes}`）保持不变；
- `test_generate_api.py::test_llm_not_configured_reflection_template`
  的 `_run_reflection` 直接 import 同步改为新入口。

## 6. 前端

- `types/agent.ts`：`review` 事件成员（替换预留占位）；
  `PendingWrite` 增加可选 `review`。
- `useAgentChat.ts`：review 事件默认入时间线（appendEvent 已有）；
  `PendingWriteView` 携带 `review`，selectSession/recover/write_confirm
  三处同步。
- `AgentWorkbench.tsx`：
  - `ReviewTimelineItem`：✓ 通过（绿）/ ✗ 打回（琥珀）徽标 + 问题列表
    （`type` 中文名：知识库边界/套话/JD 覆盖/数字无来源/其他）+ summary；
  - 写入确认卡片：`review` 存在且 `passed=false` 时渲染黄色「审查意见」区，
    逐条列出问题（不通过仍可确认——最终决定权在用户）。

## 7. 测试策略（TDD）

- `tests/test_agent_reviewer.py`（新）：
  - review_draft 通过/打回（scripted LLM JSON）、fail-open（未配置/异常/坏 JSON）；
  - review_evidence 形状兼容（issues_found/issues/notes）+ 未配置兜底。
- `tests/test_agent_runner.py`（扩展）：
  - 打回：无 write_confirm/pending_write，tool 意见闭合，LLM 重写后通过
    → gate 附 review；
  - 打回耗尽：第 3 次审查仍不合格 → 放行进 gate，pending_write.review
    如实带 issues；
  - review 事件按序发出；reviewer 异常 → 跳过审查直接 gate。
- `tests/test_agent_api.py`（扩展）：SSE 流透传 review 事件；
  会话详情 pending_write 含 review。
- `tests/test_generate_api.py`：更新 `_run_reflection` import 用例。

## 8. 风险与决策记录

- **打回不改会话状态机**：打回发生在同一 `_loop` 内（不暂停会话），
  复用 running 状态，无新状态值。
- **计数不持久化**：打回循环不跨 run/resume 存活（中断后重新审查，
  幂等且安全，最多多花一次审查）。
- **打回后同消息内其余 tool_calls 丢弃**：与 ask_user/write 门禁现状一致
  （design §2.1 agent-write-guard 已接受该限制）。
- **证据检索 query 质量**：草稿文本截断拼接即可，审查 prompt 允许证据
  为空（此时边界检查降级，不做知识库外判定）。
