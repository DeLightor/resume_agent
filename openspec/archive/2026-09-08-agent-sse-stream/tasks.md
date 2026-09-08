# Tasks: agent-sse-stream

> TDD 顺序执行：每个任务先写失败测试，再最小实现。

## 1. Runner 事件钩子

- [x] 1.1 `run/resume/_loop` 增加 `on_event` 可选回调；事件序列测试：多轮工具调用 → thinking/tool_call/tool_result 交替 + done；不传回调行为不变（既有测试回归）
- [x] 1.2 ask_user 暂停事件（tool_call + ask_user + done awaiting_user）；异常 → error 事件；轮次耗尽 → done 带提示

## 2. SSE 端点

- [x] 2.1 `POST /api/agent/chat` 骨架：校验（404 / 空 message / LLM 未配置 → JSON envelope）+ StreamingResponse 空事件流；契约测试解析 SSE 帧
- [x] 2.2 事件流接入：后台 task + asyncio.Queue；正常全流程事件顺序断言；awaiting_user 走 resume 路径
- [x] 2.3 断线收敛：客户端断开后后台任务继续，会话状态最终持久化为终态；keepalive 心跳

## 3. 前端基础设施

- [x] 3.1 `types/agent.ts`：AgentEvent 联合类型 + 会话类型
- [x] 3.2 `lib/api.ts`：Agent REST 封装 + `streamAgentChat`（fetch 流式 + SSE 帧解析）

## 4. 前端工作台

- [x] 4.1 `hooks/useAgentChat`：会话管理、发送、事件累积、断线恢复（refetch + 轮询）
- [x] 4.2 `components/agent/AgentWorkbench`：会话侧栏 + 行为时间线（工具调用可展开）+ ask_user 卡片 + 输入区
- [x] 4.3 导航接入：ActiveView 加 'agent'，NAV_TABS 加「AI 助手」，CenterPanel 分支渲染

## 5. 交付验证

- [x] 5.1 全量 pytest（backend）绿；前端 tsc + eslint + build 零错误
- [x] 5.2 HJ 冒烟：创建会话 → 对话 → 看时间线 → ask_user 问答 → 刷新恢复
- [x] 5.3 OpenSpec 归档 + 合并
