# 技术设计：project-scaffold

> **关联变更**：project-scaffold
> **设计阶段**：proposed
> **设计日期**：2026-07-04
> **关联 PRD**：`/PRD.md` v1.0

---

## 1. 设计目标

为 Resume-Agent MVP 搭建可运行、可部署、可测试的工程骨架，满足以下硬约束：

- **单容器部署**：前端 build 产物由 FastAPI 静态托管，用户只启动 1 个容器、访问 1 个端口（5173）。
- **数据落盘**：SQLite 与 Chroma 数据均落在挂载卷 `~/.resume-agent/`，容器删除数据不丢。
- **设计一致**：设计稿令牌通过 Tailwind v4 `@theme` 注入，组件用语义类名消费。
- **质量门禁**：typecheck / lint / test / Docker build 全部可在 CI 中执行。

---

## 2. 架构概览

### 2.1 部署架构（单容器）

```
┌─────────────────────────────────────────────────────────────┐
│                  Docker Container (:5173)                   │
│                                                              │
│   ┌────────────────────────────────────────────────────┐    │
│   │              FastAPI (uvicorn)                      │    │
│   │                                                      │    │
│   │   /api/*  ──→  路由层（resume/tree/knowledge/jd）    │    │
│   │                                                      │    │
│   │   /         ──→  StaticFiles(frontend/dist)          │    │
│   │   /assets/* ──→  Vite 构建产物（JS/CSS/图片）        │    │
│   └────────────────────────────────────────────────────┘    │
│           │                          │                      │
│           ▼                          ▼                      │
│   ┌──────────────┐         ┌──────────────────┐            │
│   │   SQLite     │         │  Chroma 嵌入式    │            │
│   │  data.db     │         │  PersistentClient │            │
│   │  (元数据)    │         │  (向量库)         │            │
│   └──────────────┘         └──────────────────┘            │
│           │                          │                      │
│           └──────────┬───────────────┘                      │
│                      ▼                                      │
│         挂载卷 ~/.resume-agent/  (持久化)                   │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
            云端 LLM API (OpenAI / Claude / DeepSeek)
```

**关键决策：**

1. **为什么单容器？** PRD 硬指标要求「clone 到可用 ≤15 分钟」。双容器（前端 + 后端）会让用户面对两个端口、两个进程、更复杂的 Compose 配置。单容器把前端 build 产物交给 FastAPI 静态托管，用户只需 `docker compose up` + 访问 `:5173`。
2. **为什么 Chroma 嵌入式？** 避免额外启动 Chroma server 进程。`chromadb` 的 `PersistentClient` 直接以库形式读写本地 DuckDB + Parquet 文件，数据落在挂载卷，零运维成本。
3. **为什么同端口 5173？** 避免前端跨域调用 API，开发态 Vite 也用 5173，保持开发/生产端口一致，降低心智负担。

### 2.2 开发态架构

```
开发态（make dev）
┌──────────────────────────────────────┐
│  Vite Dev Server (:5173)            │
│  ├─ /        → 前端源码热更新        │
│  └─ /api/*   → proxy → uvicorn:8000 │
└──────────────────────────────────────┘
            │ proxy
            ▼
┌──────────────────────────────────────┐
│  uvicorn (:8000)                     │
│  └─ FastAPI 热重载                    │
└──────────────────────────────────────┘
```

开发态用 Vite 的 `server.proxy` 把 `/api` 代理到 `localhost:8000`，保持开发热更新体验。生产态则由 FastAPI 直接托管前端 build 产物，关闭代理。

---

## 3. 数据库 Schema 设计

### 3.1 存储分工

| 存储 | 内容 | 位置 | 初始化方式 |
|------|------|------|-----------|
| SQLite | 版本树结构、节点元数据、上传记录 | `~/.resume-agent/data.db` | 启动时自动建表 |
| Chroma | 简历切片 + 知识素材的向量索引 | `~/.resume-agent/chroma/` | 启动时 PersistentClient 初始化 |
| 文件系统 | 原始上传文件、生成 PDF | `~/.resume-agent/files/` | 启动时确保目录存在 |

### 3.2 SQLite Schema

#### 3.2.1 `resume_versions` 表（版本树节点）

存储简历版本树的所有节点，包含主干、方向分支、公司节点。

```sql
CREATE TABLE IF NOT EXISTS resume_versions (
    -- 主键与树结构
    id              TEXT PRIMARY KEY,          -- UUID v4
    node_id         TEXT NOT NULL UNIQUE,      -- 业务节点 ID（如 master / security / tencent-rs）
    parent_id       TEXT,                       -- 父节点 ID，NULL 表示根节点(master)

    -- 节点类型与内容
    node_type       TEXT NOT NULL CHECK (node_type IN ('master', 'branch', 'company')),
    title           TEXT NOT NULL,              -- 节点显示标题（如「Master 主干」「安全岗方向」）
    company         TEXT,                       -- 仅 company 节点填写公司名
    direction       TEXT,                       -- 仅 branch 节点填写方向（如「安全」「推荐」）

    -- 简历内容（JSON Schema 规范化的结构化简历）
    content_json    TEXT,                       -- JSON: {basic, education, experience, projects, skills}

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

    -- 索引
    FOREIGN KEY (parent_id) REFERENCES resume_versions(node_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_resume_parent ON resume_versions(parent_id);
CREATE INDEX IF NOT EXISTS idx_resume_type   ON resume_versions(node_type);
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT (UUID) | 主键，技术 ID |
| `node_id` | TEXT | 业务节点 ID，用于父子关联与 URL 寻址 |
| `parent_id` | TEXT | 父节点 ID，master 为 NULL，branch 指向 master，company 指向 branch |
| `node_type` | TEXT | 节点形态：`master`(主干/青色) / `branch`(方向分支/紫色) / `company`(公司节点/橙色) |
| `title` | TEXT | 画布与面包屑显示标题 |
| `company` | TEXT | 仅 company 节点使用，公司名 |
| `direction` | TEXT | 仅 branch 节点使用，方向名（安全/推荐/NLP） |
| `content_json` | TEXT | 结构化简历 JSON，MVP 可为 NULL（空节点） |
| `created_at` | TEXT | 创建时间，ISO8601 |
| `updated_at` | TEXT | 最后更新时间 |

#### 3.2.2 `knowledge_chunks` 表（知识库切片）

存储知识素材切片的元数据，向量本身存 Chroma，本表记录映射关系。

```sql
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id              TEXT PRIMARY KEY,          -- UUID v4
    source_file     TEXT NOT NULL,              -- 来源文件名（如 "周报-2025-W30.md"）
    chunk_text      TEXT NOT NULL,              -- 切片原文（便于回查与展示）
    embedding_id    TEXT NOT NULL UNIQUE,       -- Chroma 中的向量 ID（一一对应）

    -- 元数据
    metadata_json   TEXT,                       -- JSON: {chunk_index, total_chunks, file_type, upload_time}

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_chunks(source_file);
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT (UUID) | 主键 |
| `source_file` | TEXT | 来源文件名，便于按文档聚合查询 |
| `chunk_text` | TEXT | 切片原文，检索结果展示时直接读取，无需回查 Chroma |
| `embedding_id` | TEXT | Chroma collection 中的向量 ID，与 Chroma 一一对应 |
| `metadata_json` | TEXT | 切片序号、总切片数、文件类型等元信息 |
| `created_at` | TEXT | 入库时间 |

#### 3.2.3 `upload_records` 表（上传记录）

记录所有上传文件的状态，含简历、知识素材、JD 截图。

```sql
CREATE TABLE IF NOT EXISTS upload_records (
    id              TEXT PRIMARY KEY,          -- UUID v4
    file_name       TEXT NOT NULL,              -- 原始文件名
    file_type       TEXT NOT NULL,              -- 扩展名: pdf / docx / md / txt / png / jpg
    file_path       TEXT NOT NULL,              -- 存储路径（相对 ~/.resume-agent/files/）

    -- 解析状态
    parse_status    TEXT NOT NULL DEFAULT ('pending')
                    CHECK (parse_status IN ('pending', 'parsing', 'success', 'failed', 'needs_review')),

    -- 时间戳
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_upload_status ON upload_records(parse_status);
CREATE INDEX IF NOT EXISTS idx_upload_type  ON upload_records(file_type);
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT (UUID) | 主键 |
| `file_name` | TEXT | 用户上传时的原始文件名 |
| `file_type` | TEXT | 文件类型，决定走哪条解析管线 |
| `file_path` | TEXT | 落盘后的相对路径 |
| `parse_status` | TEXT | 解析状态：`pending`(待处理) / `parsing`(解析中) / `success`(成功) / `failed`(失败) / `needs_review`(需人工确认) |
| `created_at` | TEXT | 上传时间 |

### 3.3 表关系

```
upload_records (上传记录)
       │ 1:N
       ▼
resume_versions (版本树节点)        knowledge_chunks (知识切片)
   ┌───┴───┐                              │
 master  branch                           │ N:1
   │       └── company                    ▼
                                  Chroma collection (向量)
```

- 一次上传（`upload_records`）可解析出 1 个版本节点（`resume_versions`）或多个知识切片（`knowledge_chunks`）。
- `knowledge_chunks.embedding_id` 与 Chroma collection 中的向量一一对应。

---

## 4. 目录结构设计

```
resume-agent/
├── README.md                         # 快速开始（5 行命令）
├── PRD.md                            # 产品需求文档（已有）
├── Dockerfile                        # 多阶段构建
├── docker-compose.yml                # 单容器部署
├── Makefile                          # install/dev/build/test/lint
├── .env.example                      # 配置模板
├── .gitignore
├── LICENSE                           # MIT
│
├── openspec/                         # OpenSpec 规格（本目录）
│   ├── config.yaml
│   └── changes/project-scaffold/
│       ├── proposal.md
│       ├── design.md
│       └── tasks.md
│
├── backend/                          # Python 后端
│   ├── pyproject.toml                # uv 管理依赖
│   ├── uv.lock
│   ├── README.md
│   ├── src/
│   │   └── resume_agent/
│   │       ├── __init__.py
│   │       ├── main.py               # FastAPI 入口 + 静态托管
│   │       ├── config.py            # 环境变量配置（pydantic-settings）
│   │       ├── api/                  # 路由层
│   │       │   ├── __init__.py
│   │       │   ├── router.py         # 聚合所有子路由
│   │       │   ├── resumes.py         # /api/resumes/*
│   │       │   ├── tree.py            # /api/tree/*
│   │       │   ├── knowledge.py       # /api/knowledge/*
│   │       │   ├── jd.py              # /api/jd/*
│   │       │   ├── gap.py              # /api/gap-report
│   │       │   ├── generate.py        # /api/generate
│   │       │   └── export.py          # /api/export/pdf
│   │       ├── db/                   # 数据库层
│   │       │   ├── __init__.py
│   │       │   ├── connection.py      # SQLite 连接管理
│   │       │   ├── schema.sql         # 建表 DDL
│   │       │   └── init_db.py        # 启动时自动建表
│   │       ├── rag/                  # Chroma 向量库
│   │       │   ├── __init__.py
│   │       │   ├── chroma_client.py  # PersistentClient 初始化
│   │       │   └── embeddings.py     # Embedding 调用封装
│   │       ├── parsers/              # 简历解析器（骨架，空实现）
│   │       │   └── __init__.py
│   │       └── agents/               # LangGraph 工作流（骨架，空实现）
│   │           └── __init__.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_import.py            # import 冒烟测试
│       └── test_db.py                # 建表测试
│
├── frontend/                         # React 前端
│   ├── package.json                  # pnpm 管理依赖
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── vite.config.ts                # 含 /api 代理 + 静态资源
│   ├── index.html
│   ├── public/
│   └── src/
│       ├── main.tsx                  # React 入口
│       ├── App.tsx                   # 路由根
│       ├── routes/                   # 路由级页面
│       │   ├── Workspace.tsx         # 工作台主页面
│       │   └── Onboarding.tsx        # 首次引导（骨架）
│       ├── components/               # 可复用组件
│       │   ├── layout/
│       │   │   ├── GlobalToolbar.tsx # 顶部全局工具栏
│       │   │   ├── MainLayout.tsx    # 三栏布局容器
│       │   │   ├── LeftPanel.tsx     # 左栏：导航 + 上传 + 知识库状态
│       │   │   ├── CenterPanel.tsx   # 中栏：版本树 + 面包屑
│       │   │   └── RightPanel.tsx    # 右栏：JD / Gap / 生成预览
│       │   ├── tree/
│       │   │   ├── VersionTree.tsx   # React Flow 画布
│       │   │   └── nodes/
│       │   │       ├── MasterNode.tsx
│       │   │       ├── BranchNode.tsx
│       │   │       └── CompanyNode.tsx
│       │   └── common/
│       │       ├── Breadcrumb.tsx
│       │       ├── UploadZone.tsx
│       │       └── KnowledgeStatus.tsx
│       ├── data/                    # 静态 mock 数据
│       │   ├── mockTree.ts           # 模拟版本树
│       │   └── mockJdAnalysis.ts     # 模拟 JD 分析结果
│       ├── hooks/                    # 自定义 hooks
│       │   └── useVersionTree.ts
│       ├── lib/                      # 工具库
│       │   └── api.ts               # API 调用封装（fetch wrapper）
│       ├── styles/
│       │   └── tokens.css            # 设计令牌 + Tailwind @theme
│       └── types/                    # TypeScript 类型定义
│           └── tree.ts
│
├── docs/                             # 文档
│   ├── deployment.md                 # 部署详细文档
│   ├── configuration.md              # 配置项说明
│   └── architecture.md               # 架构说明
│
└── resume-agent-workspace/           # 设计稿（保留，不改）
    ├── pages/
    ├── colors_and_type.css
    └── resume-agent-workspace.design
```

---

## 5. API 端点设计

本变更只搭端点骨架，全部返回桩数据（mock），不实现业务逻辑。端点列表对齐 PRD 第 4 节。

### 5.1 端点总览

| 端点 | 方法 | 用途 | 本变更实现 |
|------|------|------|-----------|
| `/api/health` | GET | 健康检查 + 配置状态 | 完整实现 |
| `/api/resumes/upload` | POST | 上传简历文件 | 桩（返回 mock 记录） |
| `/api/resumes/parse` | POST | 解析简历→结构化 JSON | 桩（返回 mock JSON） |
| `/api/tree` | GET | 获取版本树结构 | 桩（返回 mock 树） |
| `/api/tree/node` | POST | 新建分支/节点 | 桩（返回 mock 节点） |
| `/api/knowledge/upload` | POST | 上传知识素材 | 桩 |
| `/api/knowledge/index` | POST | 触发索引 | 桩 |
| `/api/knowledge/search` | POST | 语义检索 | 桩（返回 mock 结果） |
| `/api/jd/analyze` | POST | 上传截图→结构化提取 | 桩 |
| `/api/gap-report` | POST | 生成 Gap 报告 | 桩 |
| `/api/generate` | POST | AI 生成简历 | 桩 |
| `/api/export/pdf` | POST | 导出 PDF | 桩 |

### 5.2 健康检查端点（完整实现）

```python
# backend/src/resume_agent/api/health.py
GET /api/health

Response 200:
{
  "status": "ok",
  "version": "0.1.0-mvp",
  "db": "ready",                    # SQLite 已初始化
  "chroma": "ready",                # Chroma 已初始化
  "llm_configured": false,          # 是否已配置 LLM API Key
  "node_count": 0                   # 版本树节点数
}
```

### 5.3 版本树端点（桩实现示例）

```python
# backend/src/resume_agent/api/tree.py
GET /api/tree

Response 200 (mock):
{
  "nodes": [
    {
      "id": "master",
      "node_id": "master",
      "parent_id": null,
      "node_type": "master",
      "title": "Master 主干",
      "company": null,
      "direction": null
    },
    {
      "id": "branch-security",
      "node_id": "security",
      "parent_id": "master",
      "node_type": "branch",
      "title": "安全岗方向",
      "direction": "安全"
    },
    {
      "id": "company-tencent-rs",
      "node_id": "tencent-researcher",
      "parent_id": "security",
      "node_type": "company",
      "title": "Tencent 安全研究员",
      "company": "Tencent"
    }
  ],
  "edges": [
    {"source": "master", "target": "security"},
    {"source": "security", "target": "tencent-researcher"}
  ]
}
```

### 5.4 统一响应格式

所有 API 响应遵循统一 envelope：

```json
{
  "ok": true,
  "data": { ... },
  "error": null
}
```

错误时：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "PARSE_FAILED",
    "message": "简历解析失败，请检查文件格式"
  }
}
```

---

## 6. Chroma 嵌入式初始化方案

### 6.1 选型理由

| 方案 | 是否采用 | 原因 |
|------|---------|------|
| Chroma Server（独立进程） | 否 | 多一个进程要管，违背单容器原则 |
| Chroma PersistentClient（嵌入式） | 是 | 库形式调用，数据落盘到挂载卷，零运维 |
| Pinecone / Weaviate 云服务 | 否 | 违背「本地优先」隐私原则 |

### 6.2 初始化代码设计

```python
# backend/src/resume_agent/rag/chroma_client.py

import chromadb
from resume_agent.config import settings

_client: chromadb.PersistentClient | None = None


def get_chroma_client() -> chromadb.PersistentClient:
    """
    获取 Chroma 嵌入式客户端（单例）。
    使用 PersistentClient 模式，数据落盘到 settings.chroma_path。
    """
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_path)
    return _client


def get_resume_collection():
    """简历切片集合"""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="resume_chunks",
        metadata={"hnsw:space": "cosine"}
    )


def get_knowledge_collection():
    """知识素材切片集合"""
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="knowledge_chunks",
        metadata={"hnsw:space": "cosine"}
    )
```

### 6.3 数据落盘结构

```
~/.resume-agent/
├── data.db                          # SQLite 元数据
├── chroma/                          # Chroma 嵌入式数据
│   ├── chroma.sqlite3               # Chroma 元数据
│   └── <collection-uuid>/           # 每个集合的向量数据
│       ├── data_level0.bin
│       ├── header.bin
│       └── length.bin
└── files/                           # 上传文件 + 生成 PDF
    ├── resumes/
    └── knowledge/
```

### 6.4 启动时初始化流程

```python
# backend/src/resume_agent/main.py（节选）

@app.on_event("startup")
async def startup_event():
    """启动时自动初始化数据库与向量库"""
    # 1. SQLite 建表
    init_database(settings.sqlite_path)
    # 2. Chroma 初始化（创建客户端即触发目录创建与集合就绪）
    get_chroma_client()
    get_resume_collection()
    get_knowledge_collection()
    # 3. 确保文件目录存在
    settings.files_root.mkdir(parents=True, exist_ok=True)
```

### 6.5 Embedding 提供者

本变更只搭骨架，Embedding 调用逻辑留 `rag-index` 变更。当前 `embeddings.py` 提供接口定义：

```python
# backend/src/resume_agent/rag/embeddings.py（接口骨架）

from abc import ABC, abstractmethod

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI text-embedding-3-small，1536 维"""
    ...

# 本变更不实现具体调用，留 rag-index 变更
```

---

## 7. 前端组件拆分方案

### 7.1 组件树

```
<App>
└── <Routes>
    └── <Workspace>                          # 工作台主页面
        ├── <GlobalToolbar>                  # 顶部全局工具栏
        │   ├── Logo + 版本号
        │   ├── 导航 Tab（简历版本分支 / 知识库 / 设置）
        │   └── 右侧（状态指示 + 本地模式 chip + 头像）
        │
        └── <MainLayout>                     # 三栏布局容器
            ├── <LeftPanel>                  # 左栏 260px
            │   ├── 顶部品牌区
            │   ├── 导航列表（工作台 / 版本树 / 知识库 / JD分析 / Gap / 时间线）
            │   ├── 上传区
            │   │   ├── <UploadZone> 简历（PDF/Word）
            │   │   └── <UploadZone> 知识素材
            │   └── <KnowledgeStatus>        # 知识库状态指示器
            │
            ├── <CenterPanel>                # 中栏 flex-1
            │   ├── <Breadcrumb>              # 面包屑 master / security / tencent-rs
            │   ├── Tab Pills（版本树 / 预览 / Diff）
            │   └── <VersionTree>            # React Flow 画布
            │       ├── <MasterNode>         # 圆形 / 青色
            │       ├── <BranchNode>         # 圆角矩形 / 紫色
            │       └── <CompanyNode>        # 矩形 / 橙色
            │
            └── <RightPanel>                 # 右栏 380px
                ├── JD 分析卡片
                ├── Gap 报告列表
                └── AI 生成预览区
```

### 7.2 组件职责

| 组件 | 职责 | 本变更实现 |
|------|------|-----------|
| `GlobalToolbar` | 顶部 48px 工具栏，品牌 + 导航 + 状态 | 完整（静态） |
| `MainLayout` | 三栏 flex 布局容器，左 260 / 中 flex / 右 380 | 完整 |
| `LeftPanel` | 导航 + 上传区 + 知识库状态 | 完整（静态） |
| `CenterPanel` | 面包屑 + 版本树画布 | 完整（mock 数据） |
| `RightPanel` | JD / Gap / 生成预览 | 完整（空状态） |
| `VersionTree` | React Flow 画布，渲染节点与边 | 完整（mock 树） |
| `MasterNode` / `BranchNode` / `CompanyNode` | 自定义节点组件，区分形态与配色 | 完整 |
| `Breadcrumb` | 路径面包屑 | 完整（静态） |
| `UploadZone` | 拖拽上传区 | 完整（UI，不接后端） |
| `KnowledgeStatus` | 切片数 + 索引进度指示器 | 完整（静态） |

### 7.3 React Flow 节点设计

三种节点形态对齐设计稿配色：

| 节点类型 | 形状 | 配色（令牌） | CSS 变量 |
|---------|------|-------------|---------|
| master | 圆形 | 青色 | `--color-node-master: #0891b2` |
| branch | 圆角矩形 | 紫色 | `--color-node-branch: #7c3aed` |
| company | 矩形 | 橙色 | `--color-node-company: #d97706` |

节点组件示例：

```tsx
// frontend/src/components/tree/nodes/MasterNode.tsx
import { Handle, Position } from '@xyflow/react';

export function MasterNode({ data }: { data: { label: string } }) {
  return (
    <div className="flex items-center justify-center rounded-full
                    bg-node-master text-text-inverse shadow-glow-master
                    w-16 h-16 text-xs font-medium">
      {data.label}
      <Handle type="source" position={Position.Right} />
      <Handle type="target" position={Position.Left} />
    </div>
  );
}
```

### 7.4 路由设计

```tsx
// frontend/src/App.tsx
import { Routes, Route } from 'react-router-dom';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Workspace />} />
      <Route path="/onboarding" element={<Onboarding />} />
    </Routes>
  );
}
```

MVP 只有 workspace 一个主路由，onboarding 留骨架。

---

## 8. 设计令牌迁移方案

### 8.1 迁移目标

将 `resume-agent-workspace/colors_and_type.css` 中的设计令牌迁移到 Tailwind v4 体系，使组件能用 `bg-bg-primary` `text-text-secondary` 等语义类名直接消费。

### 8.2 迁移策略

Tailwind v4 用 `@theme` 指令在 CSS 中声明设计令牌，自动生成对应的工具类。迁移分两步：

1. **原样保留 CSS 变量**：在 `tokens.css` 的 `:root` 中保留全部 `--color-*` `--text-*` 等变量，保证设计稿 HTML 可直接复用。
2. **注入 Tailwind @theme**：用 `@theme` 把变量映射为 Tailwind 工具类，使组件能用语义类名。

### 8.3 迁移后的 tokens.css 结构

```css
/* frontend/src/styles/tokens.css */

/* === 第 1 层：原样保留设计稿 CSS 变量（兼容设计稿 HTML） === */
:root {
  --color-bg-primary: #fafbfc;
  --color-bg-secondary: #ffffff;
  --color-bg-tertiary: #f1f5f9;
  /* ... 其余颜色、字号、间距、圆角、阴影变量原样保留 ... */

  --color-node-master: #0891b2;
  --color-node-branch: #7c3aed;
  --color-node-company: #d97706;

  --font-display: 'Inter', 'SF Pro Display', -apple-system, sans-serif;
  --font-body: 'Inter', 'SF Pro Text', -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  --header-height: 48px;
  --left-panel-width: 260px;
  --right-panel-width: 380px;
}

/* === 第 2 层：Tailwind v4 @theme 注入 === */
@import "tailwindcss";

@theme {
  /* 颜色 → 生成 bg-bg-primary / text-text-secondary 等工具类 */
  --color-bg-primary: #fafbfc;
  --color-bg-secondary: #ffffff;
  --color-bg-tertiary: #f1f5f9;

  --color-text-primary: #0f172a;
  --color-text-secondary: #475569;

  --color-brand-primary: #2563eb;
  --color-brand-secondary: #7c3aed;

  --color-node-master: #0891b2;
  --color-node-branch: #7c3aed;
  --color-node-company: #d97706;

  /* 字体 → 生成 font-display / font-body / font-mono */
  --font-display: 'Inter', sans-serif;
  --font-body: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

### 8.4 生成的工具类映射

| 设计令牌 | Tailwind 工具类 | 用法示例 |
|---------|----------------|---------|
| `--color-bg-primary` | `bg-bg-primary` | `<div className="bg-bg-primary">` |
| `--color-text-secondary` | `text-text-secondary` | `<span className="text-text-secondary">` |
| `--color-brand-primary` | `bg-brand-primary` `text-brand-primary` | `<button className="bg-brand-primary">` |
| `--color-node-master` | `bg-node-master` `border-node-master` | `<div className="bg-node-master">` |
| `--font-mono` | `font-mono` | `<code className="font-mono">` |

### 8.5 Vite 配置

```ts
// frontend/vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    // 产物供 FastAPI 静态托管
  },
});
```

### 8.6 验证迁移一致性

迁移后需验证设计稿令牌与 Tailwind 工具类渲染结果一致：

- [x] `bg-bg-primary` 渲染色值 = `#fafbfc`
- [x] `text-text-secondary` 渲染色值 = `#475569`
- [x] `bg-node-master` 渲染色值 = `#0891b2`
- [x] `font-mono` 实际字体栈包含 `JetBrains Mono`

---

## 9. 配置管理设计

### 9.1 环境变量（.env.example）

```bash
# === LLM 配置 ===
LLM_PROVIDER=openai              # openai / claude / deepseek / custom
LLM_API_KEY=                     # 用户填入，仅存本地
LLM_BASE_URL=                    # 可选，支持代理 / 私有部署

# === Embedding 配置 ===
EMBEDDING_PROVIDER=openai        # openai / deepseek
EMBEDDING_MODEL=text-embedding-3-small

# === 数据存储 ===
RESUME_AGENT_HOME=~/.resume-agent
SQLITE_PATH=~/.resume-agent/data.db
CHROMA_PATH=~/.resume-agent/chroma
FILES_ROOT=~/.resume-agent/files

# === 服务 ===
HOST=0.0.0.0
PORT=5173
DEBUG=false
CORS_ORIGINS=http://localhost:5173
```

### 9.2 配置加载（pydantic-settings）

```python
# backend/src/resume_agent/config.py
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # LLM
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""

    # Embedding
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # 存储
    resume_agent_home: Path = Path.home() / ".resume-agent"
    sqlite_path: Path = Path.home() / ".resume-agent" / "data.db"
    chroma_path: Path = Path.home() / ".resume-agent" / "chroma"
    files_root: Path = Path.home() / ".resume-agent" / "files"

    # 服务
    host: str = "0.0.0.0"
    port: int = 5173
    debug: bool = False

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)

    class Config:
        env_file = ".env"
        env_prefix = ""

settings = Settings()
```

---

## 10. Docker 部署设计

### 10.1 多阶段 Dockerfile

```dockerfile
# === Stage 1: 前端构建 ===
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
RUN corepack enable && corepack prepare pnpm@latest --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build  # 产出 dist/

# === Stage 2: 后端运行时 ===
FROM python:3.11-slim AS runtime
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/src ./src
COPY --from=frontend-build /app/frontend/dist ./static

ENV RESUME_AGENT_HOME=/root/.resume-agent
EXPOSE 5173
CMD ["uv", "run", "uvicorn", "resume_agent.main:app", "--host", "0.0.0.0", "--port", "5173"]
```

### 10.2 docker-compose.yml

```yaml
services:
  resume-agent:
    build: .
    ports:
      - "5173:5173"
    volumes:
      - ~/.resume-agent:/root/.resume-agent
    environment:
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - LLM_API_KEY=${LLM_API_KEY:-}
      - LLM_BASE_URL=${LLM_BASE_URL:-}
    restart: unless-stopped
```

### 10.3 FastAPI 静态托管

```python
# backend/src/resume_agent/main.py（节选）
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="Resume-Agent")

# API 路由
app.include_router(api_router, prefix="/api")

# 静态文件托管前端 build 产物
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA 兜底：所有非 /api 路径返回 index.html"""
    return FileResponse("static/index.html")
```

---

## 11. 设计权衡与风险

| 决策点 | 选项 | 选择 | 理由 |
|--------|------|------|------|
| ORM vs 原生 SQL | SQLAlchemy / 原生 sqlite3 | 原生 sqlite3 | 减少依赖，schema 简单，避免过度抽象 |
| React Flow 版本 | v11 `reactflow` / v12 `@xyflow/react` | v12 | 长期维护，API 更稳定 |
| Tailwind 配置方式 | PostCSS 插件 / @tailwindcss/vite | @tailwindcss/vite | v4 推荐方式，零配置 |
| Chroma 集合 | 单集合 / 双集合 | 双集合 | 简历与知识素材语义不同，分集合便于召回 |
| 前端状态管理 | Redux / Zustand / Context | Zustand（后续） | 轻量，本变更暂不引入 |
| 路由方案 | React Router v6 / TanStack Router | React Router v6 | 生态成熟，文档充分 |

---

## 12. 验证清单

本变更完成后，按以下清单逐项验证：

### 12.1 后端验证
- [x] `uv run python -c "import resume_agent"` 无报错
- [x] `uv run ruff check .` 零错误
- [x] `uv run mypy src/resume_agent` 零错误
- [x] `uv run pytest` 通过（含建表测试 + import 测试）
- [x] 启动后 `~/.resume-agent/data.db` 自动创建且含 3 张表
- [x] 启动后 `~/.resume-agent/chroma/` 目录存在
- [x] `GET /api/health` 返回 200 且 db/chroma 状态为 ready

### 12.2 前端验证
- [x] `pnpm typecheck` 零错误
- [x] `pnpm lint` 零错误
- [x] `pnpm build` 成功产出 `dist/`
- [x] `pnpm dev` 后 `localhost:5173` 可访问 workspace 页面
- [x] 三栏布局可见，配色与设计稿一致
- [x] React Flow 画布渲染 mock 版本树（3 种节点形态）

### 12.3 部署验证
- [x] `docker compose build` 成功
- [x] `docker compose up` 后 5173 端口可访问
- [x] Docker 镜像大小 ≤ 500MB
- [x] 容器删除后 `~/.resume-agent/` 数据保留
- [x] `.env.example` 列出全部环境变量

### 12.4 设计令牌验证
- [x] `bg-bg-primary` 渲染色值 = `#fafbfc`
- [x] `bg-node-master` 渲染色值 = `#0891b2`
- [x] 设计稿 HTML 与 React 组件配色视觉一致

---

## 13. 参考资料

- PRD：`/PRD.md`（第 4 节技术规格、第 6 节集成端点）
- 设计稿令牌：`/resume-agent-workspace/colors_and_type.css`
- 设计稿布局：`/resume-agent-workspace/pages/workspace.html`
- OpenSpec 配置：`/openspec/config.yaml`
- 变更提案：`./proposal.md`
- 任务清单：`./tasks.md`
