# Proposal: reviewer-agent

## Why

PRD-v2.0 US-30（B1）：生成内容必须经过**独立上下文的 Reviewer Agent** 审查
才能交给用户，否则简历里会有 AI 套话和编造——这是 v2.0「诚实性结构性保证」
的核心卖点（§4.1 设计原则 2）。现状缺口：

- Agent 写入护栏（agent-write-guard）只拦「用户确认」，写入内容本身无人审查；
- 旧「反思」逻辑（`api/generate.py` `_run_reflection`）只用于传统生成流水线
  且只检查检索片段，Agent 对话路径完全没有审查；
- PRD 明确要求「既有反思逻辑迁移并入 Reviewer，删除旧实现」。

## What Changes

- **ReviewerAgent（新模块 `agents/reviewer.py`）**：
  - `review_draft(content, structured_jd, evidence)`：对**待写入草稿**做
    独立 LLM 审查（不复用 Orchestrator 对话历史），检查项：
    ① 知识库边界（素材外的内容标黄）② 套话检测 ③ JD 关键词覆盖
    ④ 量化数字无来源标记；输出 `{passed, issues[], summary}`；
  - `review_evidence(evidence)`：迁移自 `generate._run_reflection`
    （返回形状 `{issues_found, issues, notes}` 保持兼容），旧实现删除。
- **Runner 双审集成（打回循环）**：合法 `write_node` 调用在进入写入门禁前
  先过 Reviewer：
  - **不合格 → 带修改意见打回**：以 tool result 闭合该 write_node 调用回传
    LLM 重写，同一轮 run 内最多打回 2 次；
  - **通过 或 已打回 2 次仍不合格** → 进入既有写入门禁
    （`pending_write` 附带 review 结果，如实向用户展示问题）；
  - 新 SSE 事件 `review`（协议中已预留）：`{passed, round, node_id,
    issues[], summary}`；`write_confirm` 事件与 `pending_write` 增加
    `review` 字段（审查意见随 diff 一起展示）。
- **证据检索**：审查前从草稿内容提取关键词调 `search_knowledge`
  （top_k=5）取得知识库证据；`structured_jd` 取自会话 context。
- **fail-open 安全默认**：LLM 未配置 / 审查异常 → 跳过审查直接进门禁
  （审查是质量增强，不应阻塞功能可用）。
- **前端**：时间线渲染 `review` 事件（通过/打回徽标 + 问题列表）；
  写入确认卡片展示审查意见（「为什么这样改」）。

## Impact

- 后端：新增 `agents/reviewer.py`；`agents/runner.py`（门禁点前接入双审 +
  打回循环）、`api/generate.py`（反思迁移，改调 ReviewerAgent）、
  `api/agent.py`（无接口变化，pending_write 已透传 review）。
- 前端：`types/agent.ts`（review 事件 + PendingWrite.review）、
  `useAgentChat.ts`（事件处理 + pendingWrite 视图携带 review）、
  `AgentWorkbench.tsx`（review 时间线条目 + 确认卡片审查意见区）。
- 测试：`test_generate_api.py` 中直接 import `_run_reflection` 的用例
  同步改为 ReviewerAgent 新入口（OpenSpec 规则：行为变更同步更新受影响测试）。
- 兼容性：SSE `review` 为预留事件类型（前端已有 default 兜底）；
  反思迁移保持 generate 响应字段不变；无数据库结构变更。

## 回滚方案

- 后端 revert 单 commit（reviewer.py 为新文件，runner 改动集中在门禁点）；
- generate 迁移回滚即恢复旧 `_run_reflection`；
- 无 schema 变更，无数据残留风险。
