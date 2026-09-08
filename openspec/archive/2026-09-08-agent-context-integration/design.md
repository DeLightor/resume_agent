# Design: agent-context-integration

对齐 PRD-v2.0 US-29（对话式工作台）。US-28 已交付对话面板本体、
ask_user 卡片、SQLite 历史与刷新恢复；本变更补齐「工作台状态 →
对话上下文」的注入链路。

## 1. 目标与非目标

**目标**
1. 右栏快捷指令一键发起带上下文的对话（PRD 三句示例）。
2. Agent 感知：当前选中节点、已上传 JD 结构化数据、Gap 报告。
3. 会话进行中上下文可更新（切节点/换 JD 后继续对话不失联）。

**非目标**
- 全局工作台状态自动同步（不做 store/观察者；由快捷指令时机驱动）。
- Gap 报告全文注入（只注摘要：overall_score + 三色计数 + 前几条
  missing 技能，控制 token）。
- US-30 Reviewer、US-31 解析确认流。

## 2. 上下文协议

### 2.1 context 字段（chat 请求可选）

```json
{
  "session_id": "...",
  "message": "...",
  "context": {
    "current_node_id": "branch-安全",
    "structured_jd": { "job_title": "...", "tech_stack": [...] },
    "gap_summary": { "overall_score": 0.42, "missing": ["Go", "K8s"] }
  }
}
```

- 三个 key 均可选；值为 null 表示「该项已清除」。
- 前端职责：从 MainLayout 汇聚的 selectedNodeId / structuredJD /
  gapReport 组装；JD 过大时仅取结构化字段（structured 本身就是结构化
  提取产物，直接传）。

### 2.2 后端更新语义（api/agent.py）

chat 处理流在读取 session 后、run/resume 前：

1. `context is None` → 跳过（现状行为）。
2. `context == session.context`（dict 相等）→ 跳过（幂等，多轮不重复注入）。
3. 不同 → 更新 `session.context` + 持久化 + 在 `session.messages`
   追加 system 消息：
   ```
   上下文已更新：{context_json 摘要}
   ```
   随后正常走 run/resume。该 system 消息持久化，Agent 后续轮次可见。

**首次会话**：创建时（POST /sessions）context 已有注入机制
（runner.py `not session.messages` 分支），本变更不重复注入——
chat 带 context 且与 session.context 不同时才追加。

**token 控制**：structured_jd 只保留 job_title / tech_stack /
hard_skills / soft_skills / bonus_items 五个字段（raw_text 不传）；
gap_summary 由前端组装为摘要（非完整 items）。

## 3. 前端设计

### 3.1 状态汇聚（MainLayout）

- `structuredJD` 已在 MainLayout（L55）——复用。
- `gapReport`：从 RightPanel 提升到 MainLayout，RightPanel 增加
  `onGapReport` 回调（对齐 onJDAnalyzed 模式）。
- `selectedNodeId` 已在 MainLayout（L51）——复用。

### 3.2 右栏 AI 快捷指令（RightPanel 新 section）

```
┌ AI 快捷指令 ──────────────────┐
│ [针对当前 JD 优化选中节点]     │
│ [我的经历太少怎么办]           │
│ [把选中节点改得更量化]         │
│ [自定义: ______] [→]          │
└──────────────────────────────┘
```

- 前三个为固定按钮（PRD 验收原文场景）；自定义输入支持任意 prompt。
- 点击/提交 → `onQuickAsk(prompt)` 回调 → MainLayout 编排。

### 3.3 MainLayout 编排

`onQuickAsk(prompt)`：
1. 组装 context（selectedNodeId / structuredJD / gapReport →
   gap_summary 摘要）。
2. `setActiveView('agent')` + 携带 `pendingAsk = {context, prompt}`
   传给 CenterPanel → AgentWorkbench。
3. AgentWorkbench useEffect 消费 pendingAsk：创建新会话（带
   context）→ 自动 send(prompt) → 清除 pendingAsk。

**AI 助手手动对话也带上下文**：AgentWorkbench 的「新对话」与会话
内 send 均从 props 接收 latestContext（MainLayout 实时组装），
chat 请求始终携带——切节点后再发消息，Agent 能感知（§2.2 更新语义）。

### 3.4 上下文摘要显示（AgentWorkbench 状态条）

状态条增加「上下文：节点 branch-安全 · JD 后端工程师」——
从会话详情（GET /{id} 已返回 context）读取，无则显示「无」。

### 3.5 useAgentChat 扩展

- `newSession(context?)`：创建会话直接带 context（现有 API 已支持）。
- `send(message)` 内部从 `getContext()` 回调拿最新 context 附到
  chat 请求（streamAgentChat 加可选参数）。
- 会话上下文摘要：从 `getAgentSession` 返回的 context 计算（前端
  类型 AgentSessionDetail.context 已有）。

## 4. 测试策略

**后端（TDD）**
1. chat 带 context（新会话）→ session.context 更新 + messages 出现
   「上下文已更新」system 消息 + Agent 收到的消息序列含该消息。
2. chat 带 context（与已有相同）→ 不追加消息（幂等）。
3. chat 带 context（不同）→ 追加更新消息。
4. 不带 context → 行为与现状一致（既有测试回归）。
5. context 含 null 字段 → 清除语义（更新后 context 无该 key）。

**前端**
- tsc + build（无测试框架，不加依赖）；浏览器自动化冒烟。

## 5. 风险与决策记录

| 决策 | 理由 |
|------|------|
| chat 请求带 context 而非仅创建时固化 | 节点/JD 是动态状态，多轮对话需感知变化；创建时固化会过期 |
| system 消息注入而非改 runner | runner 的 context 注入机制已存在；消息历史追加让 Agent 与 traces 可见上下文变化，最小侵入 |
| 幂等跳过（dict 相等） | 避免每轮重复注入膨胀 token |
| 快捷指令新建会话而非续会话 | 上下文大变的对话语义上是新任务；PRD 三句均为「一次性指令」 |
| JD 只传结构化五字段 / Gap 只传摘要 | 控制 token；raw_text 对 Agent 价值低（结构化已含关键信息） |
