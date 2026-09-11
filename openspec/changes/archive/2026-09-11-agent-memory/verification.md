# US-35 验证报告：Agent 长期记忆

## 1. 验证目标
验证 US-35 Agent 长期记忆（Agent Long-Term Memory）功能：
1. SQLite `agent_memories` 表结构、CRUD、状态切换与去重。
2. 规则意图识别（偏好 / 纠偏 / 风格）、Fail-open 预算控制（Top-8 / ≤800 字符）。
3. 后端 API 路由（`/api/agent/memories` GET/POST/PATCH/DELETE）。
4. `AgentRunner` 与 `ReviewerAgent` 记忆注入与草稿把关。
5. 前端记忆抽屉（`MemoryDrawer`）与工作台（`AgentWorkbench`）交互体验。

---

## 2. 自动化测试结果

### 2.1 后端单元与集成测试
执行命令：
```bash
uv run --project backend pytest backend/tests/test_agent_memory.py
```
结果：
- 15 passed in 0.95s
- 覆盖用例：
  - `test_create_memory_success`: 成功创建记录及默认属性
  - `test_create_memory_validation`: 非法类型与空内容校验拦截
  - `test_create_memory_deduplication`: 相同内容活跃记忆自动去重更新时间戳
  - `test_list_memories_filtering`: 生效状态与分类筛选
  - `test_update_and_delete_memory`: 内容编辑、开关切换与删除
  - `test_get_active_memory_prompt_empty`: 空记忆安全兜底
  - `test_get_active_memory_prompt_formatting_and_caps`: 标签格式化与 Top-K/字符预算截断
  - `test_extract_memory_intent`: 对话意图识别（偏好/纠偏/风格及负样本）
  - `test_extract_memories_smart_with_llm`: 自然语言语义理解（无固定句式前缀）识别与长句拆分
  - `test_api_memories_crud`: API 端点全流程
  - `test_runner_memory_injection_and_extraction`: AgentRunner 记忆挂载与指令自动提取
  - `test_reviewer_memory_injection`: ReviewerAgent 个性化红线检测挂载
  - `test_search_and_delete_memory`: 根据文本关键词模糊检索删除、按最新记忆删除、按 ID 删除
  - `test_delete_memory_tool_in_registry`: Agent 工具集集成 `delete_memory` 与 `list_memories`
  - `test_runner_emits_memory_deleted_event`: Agent 调用删除工具后发射 `memory_deleted` SSE 事件通知前端

全量 Agent 相关测试：
```bash
uv run --directory backend pytest tests/test_agent_*.py
```
结果：
- 102 passed in 2.43s

### 2.2 后端代码规范检查 (Ruff)
执行命令：
```bash
uv run --project backend ruff check backend/src backend/tests
```
结果：
- All checks passed!（0 warnings, 0 errors）

### 2.3 前端类型检查与生产构建
执行命令：
```bash
pnpm run typecheck
pnpm run build
```
结果：
- `tsc --noEmit` 0 错误通过
- `vite build` 产物构建成功（606ms）

---

## 3. 运行服务状态
- 后端服务：运行于 `http://127.0.0.1:8000`（PID 保留）
- 前端服务：运行于 `http://127.0.0.1:5173`
