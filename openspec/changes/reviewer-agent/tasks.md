# Tasks: reviewer-agent

> TDD 顺序执行：每个任务先写失败测试，再最小实现。

## 1. ReviewerAgent（独立审查模块）

- [x] 1.1 `agents/reviewer.py`：`review_draft` 通过/打回（scripted LLM）
  + fail-open（未配置 / 异常 / 坏 JSON）测试与实现
- [x] 1.2 `review_evidence`：迁移 `_run_reflection`（形状兼容
  `{issues_found, issues, notes}`）+ 未配置兜底测试与实现；
  `generate.py` 两处调用点切换 + 删除旧实现 + 更新
  `test_generate_api.py` 直接 import 用例

## 2. Runner 双审集成

- [x] 2.1 `AgentRunner` 注入 `reviewer` 参数（默认 ReviewerAgent）
- [x] 2.2 门禁点前审查 + `review` 事件 + 打回（tool 意见闭合 write_node
  调用 + trace + 计数，无 write_confirm/pending_write）测试与实现
- [x] 2.3 打回耗尽（2 次）后放行进 gate：`pending_write.review` 如实携带
  issues；`write_confirm` 事件含 review 字段
- [x] 2.4 fail-open：reviewer 异常 → 跳过审查直接 gate
- [x] 2.5 system prompt 补充打回语义说明
- [x] 2.6 `test_agent_api.py`：SSE 透传 review 事件；会话详情
  pending_write 含 review
- [x] 2.7 冒烟发现的附属修复：awaiting_user 会话 context 更新的
  system 消息插在未闭合 tool_calls 之前（原 append 到末尾会破坏
  OpenAI 协议 → DeepSeek 400；`_pending_tool_call_index` + 测试）

## 3. 前端审查展示

- [x] 3.1 `types/agent.ts`：review 事件 + `PendingWrite.review`
- [x] 3.2 `useAgentChat.ts`：pendingWrite 视图携带 review
  （write_confirm / selectSession / recover 三处）
- [x] 3.3 `AgentWorkbench.tsx`：ReviewTimelineItem（徽标 + 问题列表 +
  summary）；确认卡片「审查意见」区（passed=false 黄色警示）

## 4. 交付验证

- [x] 4.1 后端全量 pytest 绿 + ruff/mypy 零新增问题
  （356 用例仅 2 个预存 tutor 失败，HEAD 同样失败）
- [x] 4.2 前端 tsc + build 零错误
- [x] 4.3 真实 LLM 冒烟：草稿含套话/编造 → 审查打回（4 维度全命中）→
  重写通过 → 确认卡片附审查意见；打回耗尽路径（3 次审查 2 打回后放行，
  write_confirm 如实携带 passed=false + issues）；「确认写入」后节点
  内容真实持久化
- [ ] 4.4 HJ 手工验收 + OpenSpec 归档合并
