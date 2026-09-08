# Proposal: agent-context-integration

## Why

US-28 落地的 AI 助手是「空白上下文」对话：Agent 不知道用户当前选中
哪个简历节点、上传过什么 JD、Gap 报告结论是什么——每次都要用户在
消息里重新描述。PRD-v2.0 US-29 要求 Agent 结合工作台状态对话：
「帮我针对这个 JD 优化当前节点的项目经历」一句话即达，无需指代说明。

## What Changes

- **chat 请求支持上下文注入**：`POST /api/agent/chat` 增加可选
  `context` 字段（`{current_node_id?, structured_jd?, gap_summary?}`）。
  与会话已存 context 不同时：更新 `session.context` 并在消息历史追加
  一条简短 system 消息（「上下文已更新」），Agent 可感知节点/JD 变化。
  不传时行为与现状完全一致（向后兼容）。
- **右栏「AI 快捷指令」入口**：简历工作台右栏新增 section，提供
  PRD 列举的三个快捷指令（针对 JD 优化当前节点 / 经历太少怎么办 /
  把当前节点改得更量化）+ 自定义输入框。点击后切到 AI 助手视图，
  创建**带上下文的新会话**并自动发送。
- **状态汇聚**：Gap 报告从 RightPanel 局部 state 提升到 MainLayout
  （selectedNodeId / structuredJD 已在 MainLayout，补齐 gapReport），
  供快捷指令组装 context。
- **AI 助手视图感知上下文**：AgentWorkbench 顶部状态条显示当前会话
  绑定的上下文摘要（节点/JD 标题），会话列表项标注「带上下文」。

## Impact

- 后端：`api/agent.py`（ChatRequest 加字段 + 更新逻辑）、
  `agents/runner.py` 不变（context 注入机制已存在）。
- 前端：`MainLayout.tsx`（gapReport 状态提升 + 视图切换编排）、
  `RightPanel.tsx`（AI 快捷指令 section）、`useAgentChat.ts`
  （newSessionWithContext + 预填首条消息）、`AgentWorkbench.tsx`
  （上下文摘要显示）、`lib/api.ts`（streamAgentChat 带 context）。
- 兼容性：chat 端点新字段可选；既有 AI 助手手动对话流不变；
  传统按钮流不删（PRD 验收）。
- 无数据库变更（context_json 已存在，语义扩展）。

## 回滚方案

- 后端：context 字段为可选透传，revert 单 commit 即可。
- 前端：右栏 section 与状态提升为纯增量，revert 即可。
- 数据：context_json 存的字典多了几个 key，旧代码读取不受影响。
