# Tasks: agent-context-integration

> TDD 顺序执行：每个任务先写失败测试，再最小实现。

## 1. 后端 chat 上下文注入

- [x] 1.1 ChatRequest 加可选 context 字段；更新语义（不同→更新 context + 追加 system 消息；相同/缺省→跳过）；null 字段清除；5 个契约测试
- [x] 1.2 既有 chat 测试回归（不带 context 行为不变）+ runner 不改的注入验证（新会话首条 context 已有机制）

## 2. 前端状态汇聚

- [x] 2.1 gapReport 提升到 MainLayout（RightPanel 加 onGapReport 回调，对齐 onJDAnalyzed 模式）
- [x] 2.2 RightPanel 新增「AI 快捷指令」section（三个固定按钮 + 自定义输入），onQuickAsk 回调

## 3. 前端上下文流转

- [x] 3.1 streamAgentChat / useAgentChat：send 携带 getContext() 最新上下文；newSession(context)
- [x] 3.2 MainLayout 编排 onQuickAsk：组装 context → 切 agent 视图 → pendingAsk 传递 → 自动发送；AgentWorkbench 消费 pendingAsk
- [x] 3.3 AgentWorkbench 状态条显示上下文摘要（节点/JD 标题）

## 4. 交付验证

- [x] 4.1 后端全量 pytest 绿；前端 tsc + build 零错误
- [x] 4.2 浏览器自动化冒烟：右栏快捷指令 → AI 视图自动发送 → 上下文摘要显示 → Agent 响应引用上下文
- [x] 4.3 HJ 手工验收 + OpenSpec 归档合并
- [x] 4.4 验收反馈修复：done 会话续聊（对话式连续性）+ 历史会话回放（用户气泡 + assistant 回复）+ 错误去重（时间线与底部不双显）
