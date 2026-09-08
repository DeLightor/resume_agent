# Proposal: agent-runtime

> 变更状态：proposed | 风险分级：High（新数据库表 + 核心运行时）| 关联：PRD-v2.0.md US-27

## Why

v2.0 转型的地基。当前 AI 能力是散落在各 REST 端点里的单次 LLM 调用与固定函数链（检索→反思→撰写），LLM 无法自主决定调用什么、调用几轮。要把项目变成 Agent 核心，第一步是把现有后端能力封装为统一 schema 的工具，并实现一个能持久化会话、记录 trace、支持暂停恢复的 Agent Runtime。

没有本变更，US-28（SSE 行为面板）、US-29（对话工作台）、US-30（Reviewer）都无从谈起。

## What Changes

**新增（均为纯后端，无前端改动）**：

1. `agents/` 模块：
   - `Tool` 协议（name / description / parameters schema / execute）与 `ToolRegistry`
   - `AgentRunner`：基于 DeepSeek function calling 的多轮循环，最大轮数可配置（默认 8）
   - `ask_user` 特殊工具：Agent 主动暂停等待用户输入，会话状态可持久化恢复
2. `tools/` 模块：封装 9 个工具（8 个业务工具 + ask_user）
3. `db/schema.sql`：新增 `agent_sessions`、`agent_traces` 两表（幂等建表）
4. `api/agent.py`：会话 REST 端点（同步 JSON 版本，SSE 属 US-28）
5. `config.py`：新增 `agent_max_rounds` 配置项

**复用现有能力（零行为变更）**：

- `LLMClient`：新增 `chat_raw()` 单轮调用方法，既有 `chat` / `chat_with_tools` 不动
- 知识库检索、JD 结构化、Gap 分析、节点读写、模板列表、PDF 导出、Tavily 搜索：从现有 API 层抽为可复用函数后封装

## Impact

| 面 | 影响 |
|----|------|
| 数据库 | 新增 2 表（`agent_sessions` / `agent_traces`），不改既有表 |
| API | 新增 4 个端点（`/api/agent/sessions*`），不影响既有端点 |
| 既有行为 | 无变更——不修改任何现有端点逻辑，仅从 API 层抽取函数 |
| 依赖 | 无新依赖（openai SDK 已支持 function calling） |

## 明确不做（scope 边界）

- SSE / WebSocket 流式输出（US-28）
- Reviewer Agent（US-30）
- 前端对话 UI / 行为面板（US-28/29）
- Agent 记忆（US-35）

## Rollback

- 本变更为纯新增（新表、新模块、新端点），回滚 = 删除新增代码，无既有功能回归风险
- 新表无人写入即无数据残留；`schema.sql` 建表幂等，回滚后重新执行不影响旧表
- API 端点未被任何前端调用前删除，零影响
