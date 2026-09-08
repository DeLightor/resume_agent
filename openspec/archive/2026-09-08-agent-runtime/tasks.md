# Tasks: agent-runtime

> TDD 顺序执行：每个任务先写失败测试，再最小实现。全部完成后进入交付验证。

## 1. 数据层

- [x] 1.1 schema.sql 追加 `agent_sessions` / `agent_traces` 建表语句；测试：`init_db` 后 `list_tables()` 包含两表，且重复 init 幂等
- [x] 1.2 `db/` 新增 session/trace CRUD 辅助函数（或放 agents/store.py）；测试：session 状态迁移读写往返、trace 写入与按 session 查询

## 2. LLM 层

- [x] 2.1 `LLMClient.chat_raw(messages, tools=None) -> ChatCompletionMessage`：单轮调用，返回原始 message（含 tool_calls）；测试：mock AsyncOpenAI，验证 messages/tools 透传与返回；既有 chat / chat_with_tools 测试保持绿
- [x] 2.2 `config.py` 新增 `agent_max_rounds: int = 8`；测试：默认值与环境变量覆盖

## 3. 工具层

- [x] 3.1 `agents/registry.py`：ToolSpec + ToolRegistry（register / schemas 转 OpenAI 格式 / execute 异常返回 error 不中断）；测试：schema 转换、未知工具、执行异常路径
- [x] 3.2 `services/knowledge_search.py`：从 generate.py 抽 `_search_knowledge_base`；generate.py 改调公共函数；既有 generate 相关测试保持绿；`retrieve_knowledge` 工具注册
- [x] 3.3 `services/jd_extract.py`：从 jd.py 抽 JD 文本结构化 LLM 逻辑；`parse_jd` 工具注册；既有 jd 测试保持绿
- [x] 3.4 `services/gap_analyzer.py`：从 gap_report.py 抽 Gap 分析核心；`analyze_gap` 工具注册；既有 gap 测试保持绿
- [x] 3.5 `read_node` / `write_node` 工具：复用 tree 查询与 `_save_node_content` 抽取的公共函数；测试覆盖存在/不存在节点
- [x] 3.6 `list_templates` / `export_pdf` 工具：薄封装既有实现；export 失败返回 error 不中断
- [x] 3.7 `web_search` 工具：直接注册 `tavily_search.search_web`；Tavily 未配置时返回提示性空结果
- [x] 3.8 `ask_user` 工具 spec（仅 schema，执行由 Runner 特判）

## 4. Runner

- [x] 4.1 `agents/runner.py` AgentRunner 基本循环：mock chat_raw 脚本化（无 tool_calls 直接终结）；验证 messages 持久化与 status=done
- [x] 4.2 多轮工具调用：LLM 先返回 tool_calls 再返回终结消息；验证 trace 落库（round 编号、输入输出）
- [x] 4.3 ask_user 暂停：LLM 返回 ask_user 调用 → status=awaiting_user、pending_question 持久化、循环中断
- [x] 4.4 ask_user 恢复：POST 回答后从持久化 messages 续跑至终结；非法恢复（缺 tool result）→ failed
- [x] 4.5 轮次耗尽：强制无 tools 最终响应；trace 完整可查
- [x] 4.6 工具执行异常：error 作为 tool result 回传，循环继续

## 5. API 层

- [x] 5.1 `api/agent.py` 四端点（POST/GET sessions、GET 详情、POST messages）+ router 注册；契约测试（mock AgentRunner）：正常、awaiting_user、404、LLM 未配置错误
- [x] 5.2 LLM 未配置时返回明确错误信息（对齐既有端点风格）

## 6. 交付验证

- [x] 6.1 全量 `pytest`（backend）绿，ruff / mypy（新增代码）零错误
- [x] 6.2 手动冒烟：配置 LLM key，创建会话→对话触发工具调用→查看 trace（HJ 验收）
- [ ] 6.3 tasks 全勾 → OpenSpec 归档 → HJ 确认合并
