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

    -- US-17: 上游变更检测
    has_upstream_update  INTEGER DEFAULT 0,    -- 0/1: 是否有上游 personal_info 变更待合并
    upstream_changes     TEXT,                 -- JSON: {field: {old, new}} 变更详情

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

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_upload_status ON upload_records(parse_status);
CREATE INDEX IF NOT EXISTS idx_upload_type  ON upload_records(file_type);
