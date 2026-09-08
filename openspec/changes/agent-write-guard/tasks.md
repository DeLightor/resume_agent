# Tasks: agent-write-guard

> TDD 顺序执行：每个任务先写失败测试，再最小实现。

## 1. 后端门禁与仲裁

- [x] 1.1 store：`AgentSession.pending_write` 字段 + `agent_sessions` 新列
  `pending_write_json`（schema.sql + init_db 幂等迁移）+ 序列化往返测试
- [x] 1.2 runner：合法 write_node 调用 → 门禁暂停（awaiting_user +
  pending_write 持久化 + write_confirm 事件 + 不写入）测试与实现
- [x] 1.3 runner：resume 仲裁——确认词表纯函数（表驱动测试）+ 「确认」
  执行写入 / 自由文本不写入且 user_reply 回传 / trace 记录
- [x] 1.4 runner：非法参数 write_node 不触发门禁（错误 tool result 原路返回）
- [x] 1.5 prompt 与 write_node 工具描述更新；会话详情端点返回 pending_write

## 2. 前端确认交互

- [x] 2.1 types/agent.ts：`write_confirm` 事件 + 会话详情 `pending_write` 字段
- [x] 2.2 useAgentChat：write_confirm 事件处理 + pendingWrite 状态 +
  selectSession/recover 恢复
- [x] 2.3 AgentWorkbench：时间线 write_confirm 条目（内容预览可折叠）+
  底部写入确认卡片（[确认写入] / [暂不写入] / 修改意见输入）

## 3. 交付验证

- [x] 3.1 后端全量 pytest 绿 + ruff/mypy 零新增问题
  （仅 Tavily 配额导致的 2 个预存 tutor 测试失败，与本变更无关）
- [x] 3.2 前端 tsc + build 零错误
- [x] 3.3 浏览器冒烟：让 Agent 发起写入 → 确认卡片出现 → 拒绝不写 →
  再次发起 → 确认写入 → 节点内容变化
  （已用真实 LLM + 隔离库脚本冒烟通过：门禁暂停 / 确认落盘 / 自由文本拒绝；
  浏览器 UI 交互待 HJ 验收时一并确认）
- [ ] 3.4 HJ 手工验收 + OpenSpec 归档合并
