# US-35 设计方案：Agent 长期记忆

状态：已于讨论阶段向 HJ 汇报并获得开工确认。

## 1. 数据模型设计 (SQLite)
在 SQLite 中建立 `agent_memories` 数据表：
```sql
CREATE TABLE IF NOT EXISTS agent_memories (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('preference', 'correction', 'style_sample')),
    content TEXT NOT NULL,
    source TEXT DEFAULT 'auto_inferred',
    session_id TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_active ON agent_memories(active, updated_at DESC);
```

### 字段说明：
- `id`: UUID 字符串主键。
- `type`:
  - `preference`: 用户通用偏好（如「优先使用量化数据」、「强调高并发架构」）。
  - `correction`: 历史纠偏/红线（如「严禁写熟练掌握，统一写精通」、「不要出现具体薪资期望」）。
  - `style_sample`: 语言/句式习惯（如「动作动词+业务背景+指标结果 STAR 结构」）。
- `content`: 具体的记忆规则描述。
- `source`: `auto_inferred`（对话中自动识别沉淀）或 `manual`（用户手动创建）。
- `session_id`: 产生该条记忆的会话 ID（可选）。
- `active`: 1 为生效中，0 为已禁用。

## 2. 记忆抽取与维护逻辑 (`memory_store.py`)
- 提供底层存储访问类或函数模块 `MemoryStore`：
  - `list_memories(active_only: bool = False, type_filter: str | None = None) -> list[MemoryItem]`
  - `create_memory(content: str, type: str, source: str = "manual", session_id: str | None = None) -> MemoryItem`
  - `update_memory(memory_id: str, content: str | None = None, active: bool | None = None) -> MemoryItem | None`
  - `delete_memory(memory_id: str) -> bool`
  - `get_active_prompt_section(max_items: int = 8, max_chars: int = 800) -> str`
- 规则抽取机制（LLM 智能语义理解 + 规则兜底）：
  - 无需特定固定句式开头：AI 在收到用户发言时，通过独立分析器对自然语言进行语义理解，自动判断是否夹杂对简历内容、风格习惯、表达偏好或行为边界的看法与要求。
  - 支持复杂长句自然抽取与多规则拆分（例如「刚才那段太啰嗦了，我技术栈千万别写精通，另外经历多突出高并发」可自动提炼出纠偏与偏好两条规则）。
  - 自动归类为 `preference`（偏好）、`correction`（纠偏红线）或 `style_sample`（风格习惯），去重并沉淀入库。
  - 当 LLM 未配置或异常时，自动平滑降级至关键词/正则兜底规则。
  - 亦支持前端在「🧠 长期记忆」抽屉面板中手动录入。

## 3. 记忆注入策略 (Prompt Injection)
- **目标组件**：
  1. `AgentRunner`：在生成系统提示词时挂载【用户长期偏好与历史纠偏】分块。
  2. `ReviewerAgent`：在审查评估提示词时挂载【个性化红线与风格要求】分块。
- **预算保护与 Fail-Open**：
  - 仅选取 `active == 1` 的记忆项，按 `updated_at DESC` 排序取前 8 条。
  - 单次注入字符总长限制在 800 字符内（约 400 token），防止 Context 占用过大。
  - 若查询数据库异常，捕获异常并返回空字符串，保证核心会话与审查流程永远可用（Fail-Open）。

## 4. 后端 API 接口设计
- `GET /api/agent/memories`：获取全部或生效记忆列表。
- `POST /api/agent/memories`：手动或接口新增记忆。
- `PATCH /api/agent/memories/{memory_id}`：更新记忆内容或切换 active 状态。
- `DELETE /api/agent/memories/{memory_id}`：删除指定记忆。

## 5. 前端交互设计 (`MemoryDrawer.tsx` & `AgentWorkbench.tsx`)
- **入口按钮**：在 `AgentWorkbench` 右上角工具栏（与版本历史并列）提供「🧠 记忆 (N)」按钮，徽章显示当前生效条数。
- **抽屉面板（Drawer）**：
  - **顶部**：标题「Agent 长期记忆」、说明文案，以及「+ 添加规则」按钮。
  - **列表展示**：
    - 按分类展示 Tag（偏好 / 纠偏 / 风格），展示来源（系统提炼 / 手动添加）。
    - 提供 Switch 开关，可实时一键启用/禁用单条规则。
    - 提供编辑（Edit）和删除（Delete）操作。
  - **新增/编辑弹窗或内联表单**：
    - 快速选择类型、输入规则内容、保存。
