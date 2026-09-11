-- Resume-Agent SQLite Schema
-- 对齐 design.md 第 3.2 节
-- 所有建表语句使用 IF NOT EXISTS，保证幂等。

-- ========================================
-- 1. resume_versions：版本树节点
-- ========================================
CREATE TABLE IF NOT EXISTS resume_versions (
    -- 主键与树结构
    id              TEXT PRIMARY KEY,          -- UUID v4（技术主键）
    node_id         TEXT NOT NULL UNIQUE,      -- 业务节点 ID（master / security / tencent-rs）
    parent_id       TEXT,                      -- 父节点 ID，NULL 表示根节点(master)

    -- 节点类型与内容
    node_type       TEXT NOT NULL CHECK (node_type IN ('master', 'branch', 'company')),
    title           TEXT NOT NULL,             -- 节点显示标题
    company         TEXT,                      -- 仅 company 节点填写公司名
    direction       TEXT,                      -- 仅 branch 节点填写方向（如「安全」「推荐」）

    -- 简历内容（JSON Schema 规范化的结构化简历）
    content_json    TEXT,                      -- JSON: {basic, education, experience, projects, skills}

    version         INTEGER NOT NULL DEFAULT 0,
    history_cursor  INTEGER,
    deleted_at      TEXT,
    delete_batch    TEXT,

    -- US-17: 上游变更检测
    has_upstream_update  INTEGER DEFAULT 0,    -- 0/1: 是否有上游 personal_info 变更待合并
    upstream_changes     TEXT,                 -- JSON: {field: {old, new}} 变更详情
    upstream_baseline_json TEXT,               -- US-33: direct-parent common base content
    upstream_source_id   TEXT,                 -- US-33: direct parent used for the snapshot
    upstream_source_version INTEGER,            -- US-33: version displayed with the snapshot

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

    -- 外键：父节点指向 resume_versions.node_id，级联删除
    FOREIGN KEY (parent_id) REFERENCES resume_versions(node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_resume_parent ON resume_versions(parent_id);
CREATE INDEX IF NOT EXISTS idx_resume_type   ON resume_versions(node_type);

-- ========================================
-- 2. knowledge_chunks：知识库切片
-- ========================================
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              TEXT PRIMARY KEY,          -- UUID v4
    source_file     TEXT NOT NULL,             -- 来源文件名（如 "周报-2025-W30.md"）
    chunk_text      TEXT NOT NULL,             -- 切片原文（便于回查与展示）
    embedding_id    TEXT NOT NULL UNIQUE,      -- Chroma 中的向量 ID（一一对应）

    -- 元数据
    metadata_json   TEXT,                      -- JSON: {chunk_index, total_chunks, file_type, upload_time}

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_chunks(source_file);

-- ========================================
-- 3. upload_records：上传记录
-- ========================================
CREATE TABLE IF NOT EXISTS upload_records (
    id              TEXT PRIMARY KEY,          -- UUID v4
    file_name       TEXT NOT NULL,             -- 原始文件名
    file_type       TEXT NOT NULL,             -- 扩展名: pdf / docx / md / txt / png / jpg
    file_path       TEXT NOT NULL,             -- 存储路径（相对 ~/.resume-agent/files/）

    -- 解析状态
    parse_status    TEXT NOT NULL DEFAULT ('pending')
                    CHECK (parse_status IN ('pending', 'parsing', 'success', 'failed', 'needs_review')),
    direction       TEXT,

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ========================================
-- 4. parse_tasks：两阶段解析任务（US-31 parse-confirm-flow）
-- ========================================
CREATE TABLE IF NOT EXISTS parse_tasks (
    id              TEXT PRIMARY KEY,           -- 任务 ID（UUID v4）
    upload_id       TEXT NOT NULL,              -- 关联 upload_records.id
    status          TEXT NOT NULL DEFAULT 'extracting'
                    CHECK (status IN ('extracting', 'awaiting_confirm', 'confirmed', 'failed')),
    raw_text        TEXT,                       -- 提取的简历原文（确认后才写知识库）
    parser_used     TEXT,                       -- 文件解析器：mineru / local
    degraded        INTEGER NOT NULL DEFAULT 0, -- MinerU 降级到本地解析器标记
    result_json     TEXT,                       -- JSON: {structured_resume, confidence}
    knowledge_personal_json TEXT,               -- JSON: 知识库个人信息（供覆盖选择，不静默覆盖）
    error           TEXT,                       -- 失败原因

    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (upload_id) REFERENCES upload_records(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_parse_tasks_upload ON parse_tasks(upload_id);

-- ========================================
-- 5. agent_sessions：Agent 会话（US-27 agent-runtime）
-- ========================================
CREATE TABLE IF NOT EXISTS agent_sessions (
    id               TEXT PRIMARY KEY,          -- UUID v4
    status           TEXT NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running', 'awaiting_user', 'done', 'failed')),
    context_json     TEXT,                      -- JSON: {current_node_id, jd_summary, ...}
    messages_json    TEXT NOT NULL DEFAULT '[]',-- JSON: OpenAI 协议消息数组（含 tool_calls / tool results）
    pending_question TEXT,                      -- awaiting_user 时的待答问题
    pending_write_json TEXT,                    -- agent-write-guard: JSON {tool_call_id, node_id, content} 待确认写入

    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_status ON agent_sessions(status);

-- ========================================
-- 6. agent_traces：Agent 工具调用轨迹（US-27 agent-runtime）
-- ========================================
CREATE TABLE IF NOT EXISTS agent_traces (
    id              TEXT PRIMARY KEY,           -- UUID v4
    session_id      TEXT NOT NULL,
    round           INTEGER NOT NULL,           -- 第几轮 LLM 调用
    tool_name       TEXT NOT NULL,
    input_json      TEXT,                       -- JSON: 工具入参
    output_json     TEXT,                       -- JSON: 工具输出（截断至 4KB）

    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_agent_traces_session ON agent_traces(session_id);

CREATE INDEX IF NOT EXISTS idx_upload_status ON upload_records(parse_status);
CREATE INDEX IF NOT EXISTS idx_upload_type  ON upload_records(file_type);

-- US-32: bounded per-node content history.
CREATE TABLE IF NOT EXISTS node_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL REFERENCES resume_versions(node_id) ON DELETE CASCADE,
    content_json TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_node_history_node ON node_history(node_id, id);

-- US-33: committed invalidation feed for open version-tree clients.
CREATE TABLE IF NOT EXISTS tree_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_ids TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tree_events_id ON tree_events(id);
