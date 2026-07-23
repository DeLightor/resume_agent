# 任务清单：project-scaffold

> **关联变更**：project-scaffold
> **关联设计**：`./design.md`
> **状态**：pending
> **最后更新**：2026-07-04

---

## 使用说明

- 任务按分组顺序推进，组内任务可并行
- 每完成一项，将 `[ ]` 改为 `[x]`
- 全部勾选后，本变更进入「待归档」状态，等待 design review + CI 绿灯后归档
- 任务编号格式：`T<组号>.<序号>`（如 `T1.2` 表示第 1 组第 2 项）

---

## 第 1 组：工具链检查

> 目标：确认本地开发环境满足要求，避免后续步骤因版本不符失败。

- [x] **T1.1** 检查 Python 版本 `>=3.11`
  - 命令：`python --version`
  - 预期：`Python 3.11.x` 或更高
- [x] **T1.2** 检查 uv 是否安装
  - 命令：`uv --version`
  - 预期：已安装，版本符合最新稳定版
  - 若未安装：`curl -LsSf https://astral.sh/uv/install.sh | sh`
- [x] **T1.3** 检查 Node 版本 `>=20`
  - 命令：`node --version`
  - 预期：`v20.x.x` 或更高
- [x] **T1.4** 检查 pnpm 是否安装
  - 命令：`pnpm --version`
  - 预期：已安装
  - 若未安装：`corepack enable && corepack prepare pnpm@latest --activate`
- [x] **T1.5** 检查 Docker 与 Docker Compose
  - 命令：`docker --version && docker compose version`
  - 预期：Docker 已运行，Compose v2 可用
- [x] **T1.6** 记录环境信息到 `docs/environment-check.md`
  - 内容：各工具版本号、操作系统、架构（arm64/amd64）

---

## 第 2 组：后端初始化

> 目标：搭建 Python 后端骨架，可 `uv run` 启动 FastAPI。

- [x] **T2.1** 创建 `backend/pyproject.toml`
  - 项目名：`resume-agent`
  - Python 要求：`>=3.11`
  - 核心依赖：`fastapi`, `uvicorn[standard]`, `chromadb`, `langchain`, `langgraph`, `pymupdf`, `python-docx`, `pydantic`, `pydantic-settings`
  - 开发依赖：`ruff`, `mypy`, `pytest`, `pytest-asyncio`, `httpx`
  - 构建系统：`hatchling`
- [x] **T2.2** 创建后端目录结构 `backend/src/resume_agent/`
  ```
  src/resume_agent/
  ├── __init__.py
  ├── main.py
  ├── config.py
  ├── api/
  │   ├── __init__.py
  │   ├── router.py
  │   ├── health.py
  │   ├── resumes.py
  │   ├── tree.py
  │   ├── knowledge.py
  │   ├── jd.py
  │   ├── gap.py
  │   ├── generate.py
  │   └── export.py
  ├── db/
  │   ├── __init__.py
  │   ├── connection.py
  │   ├── schema.sql
  │   └── init_db.py
  ├── rag/
  │   ├── __init__.py
  │   ├── chroma_client.py
  │   └── embeddings.py
  ├── parsers/
  │   └── __init__.py
  └── agents/
      └── __init__.py
  ```
- [x] **T2.3** 实现 `backend/src/resume_agent/config.py`
  - 使用 `pydantic-settings.BaseSettings`
  - 字段：llm_provider, llm_api_key, llm_base_url, embedding_provider, embedding_model, resume_agent_home, sqlite_path, chroma_path, files_root, host, port, debug
  - 从 `.env` 文件读取
  - 导出单例 `settings`
  - 参考：`design.md` 第 9 节
- [x] **T2.4** 实现 `backend/src/resume_agent/main.py`
  - 创建 `FastAPI` 实例，title="Resume-Agent"
  - 挂载 `/api` 路由（include_router）
  - 注册 startup 事件：初始化 SQLite + Chroma + 文件目录
  - 静态文件托管：`/assets` 指向 `static/assets`
  - SPA 兜底：非 `/api` 路径返回 `static/index.html`
  - 参考：`design.md` 第 10.3 节
- [x] **T2.5** 实现 API 路由层（桩实现）
  - `api/router.py`：聚合所有子路由，统一 `/api` 前缀
  - `api/health.py`：`GET /api/health` 完整实现，返回状态 + db/chroma 就绪状态
  - `api/tree.py`：`GET /api/tree` 返回 mock 版本树，`POST /api/tree/node` 返回 mock 节点
  - `api/resumes.py` `api/knowledge.py` `api/jd.py` `api/gap.py` `api/generate.py` `api/export.py`：桩，返回 mock 数据
  - 统一响应 envelope：`{ok, data, error}`
  - 参考：`design.md` 第 5 节
- [x] **T2.6** 运行 `uv sync` 安装依赖
  - 预期：生成 `uv.lock`，`backend/.venv` 创建
- [x] **T2.7** 启动验证
  - 命令：`uv run uvicorn resume_agent.main:app --reload --port 8000`
  - 预期：`localhost:8000/api/health` 返回 200 + `{"status":"ok",...}`

---

## 第 3 组：数据库初始化

> 目标：SQLite 三张表 + Chroma 嵌入式初始化，启动时自动建表。

- [x] **T3.1** 编写 `backend/src/resume_agent/db/schema.sql`
  - `resume_versions` 表：id, node_id, parent_id, node_type, title, company, direction, content_json, created_at, updated_at
  - `knowledge_chunks` 表：id, source_file, chunk_text, embedding_id, metadata_json, created_at
  - `upload_records` 表：id, file_name, file_type, file_path, parse_status, created_at
  - 含索引：idx_resume_parent, idx_resume_type, idx_knowledge_source, idx_upload_status, idx_upload_type
  - 参考：`design.md` 第 3.2 节
- [x] **T3.2** 实现 `backend/src/resume_agent/db/connection.py`
  - 使用原生 `sqlite3` 模块（不引入 SQLAlchemy）
  - 连接路径来自 `settings.sqlite_path`
  - 提供 `get_connection()` 上下文管理器
  - 启用 `PRAGMA foreign_keys = ON`（支持级联删除）
- [x] **T3.3** 实现 `backend/src/resume_agent/db/init_db.py`
  - 读取 `schema.sql` 执行建表
  - 幂等：`CREATE TABLE IF NOT EXISTS`
  - 提供 `init_database(db_path)` 函数，被 `main.py` startup 调用
  - 建表后写入初始 master 节点（若表为空）
- [x] **T3.4** 实现 `backend/src/resume_agent/rag/chroma_client.py`
  - `get_chroma_client()`：单例 PersistentClient，path=`settings.chroma_path`
  - `get_resume_collection()`：get_or_create_collection("resume_chunks", cosine)
  - `get_knowledge_collection()`：get_or_create_collection("knowledge_chunks", cosine)
  - 参考：`design.md` 第 6.2 节
- [x] **T3.5** 实现 `backend/src/resume_agent/rag/embeddings.py`
  - 定义 `EmbeddingProvider` 抽象基类
  - `OpenAIEmbedding` 类骨架（不实现具体调用，留 rag-index 变更）
  - 参考：`design.md` 第 6.5 节
- [x] **T3.6** 编写数据库测试 `backend/tests/test_db.py`
  - 测试：建表后三张表存在
  - 测试：插入 resume_versions 记录并查询
  - 测试：parent_id 外键级联删除
  - 测试：node_type CHECK 约束生效
- [x] **T3.7** 启动验证
  - 启动后端，检查 `~/.resume-agent/data.db` 存在且含 3 张表
  - 检查 `~/.resume-agent/chroma/` 目录存在
  - 检查 `~/.resume-agent/files/` 目录存在
  - `GET /api/health` 返回 `db: ready, chroma: ready`

---

## 第 4 组：前端初始化

> 目标：搭建 Vite + React + TS + Tailwind v4 骨架，可 `pnpm dev` 启动。

- [x] **T4.1** 初始化 Vite 项目
  - 命令：`pnpm create vite frontend --template react-ts`
  - 产出：`frontend/` 目录，含 `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`
- [x] **T4.2** 配置 `frontend/package.json` 依赖
  - 运行时：`react`, `react-dom`, `react-router-dom`, `@xyflow/react`
  - 开发：`typescript`, `vite`, `@vitejs/plugin-react`, `tailwindcss@4`, `@tailwindcss/vite`
  - 测试：`vitest`, `@testing-library/react`, `@playwright/test`, `jsdom`
  - lint：`eslint`, `@typescript-eslint/parser`, `prettier`
  - 脚本：`dev`, `build`, `typecheck`, `lint`, `test`
- [x] **T4.3** 配置 `frontend/vite.config.ts`
  - 插件：`@vitejs/plugin-react`, `@tailwindcss/vite`
  - alias：`@` → `./src`
  - dev server：port 5173
  - proxy：`/api` → `http://localhost:8000`（开发态）
  - build：`outDir: dist`
  - 参考：`design.md` 第 8.5 节
- [x] **T4.4** 配置 `frontend/tsconfig.json`
  - `strict: true`
  - `jsx: react-jsx`
  - paths：`@/*` → `./src/*`
  - `noUnusedLocals`, `noUnusedParameters`: true
- [x] **T4.5** 创建前端目录结构
  ```
  src/
  ├── main.tsx
  ├── App.tsx
  ├── routes/
  │   ├── Workspace.tsx
  │   └── Onboarding.tsx
  ├── components/
  │   ├── layout/
  │   ├── tree/
  │   └── common/
  ├── data/
  ├── hooks/
  ├── lib/
  ├── styles/
  └── types/
  ```
- [x] **T4.6** 实现路由 `frontend/src/App.tsx` 与入口 `main.tsx`
  - `App.tsx`：`<Routes>` 包含 `/` → Workspace，`/onboarding` → Onboarding
  - `main.tsx`：挂载 `<App />` 到 `#root`，引入 `styles/tokens.css`
  - 参考：`design.md` 第 7.4 节
- [x] **T4.7** 运行 `pnpm install`
  - 预期：生成 `pnpm-lock.yaml`
- [x] **T4.8** 启动验证
  - 命令：`pnpm dev`
  - 预期：`localhost:5173` 返回空白 React 页面（无报错）

---

## 第 5 组：设计令牌迁移

> 目标：将 `colors_and_type.css` 令牌迁移至 Tailwind v4 `@theme` 体系。

- [x] **T5.1** 创建 `frontend/src/styles/tokens.css`
  - 第 1 层：`:root` 原样保留全部 CSS 变量（兼容设计稿 HTML）
    - 颜色：bg-*, text-*, border-*, brand-*, node-*, state-*
    - 字体：--font-display, --font-body, --font-mono
    - 字号：--text-xs ~ --text-3xl 及对应 leading
    - 间距、圆角、阴影、过渡、布局尺寸
  - 第 2 层：`@import "tailwindcss"` + `@theme { ... }` 注入
    - 颜色变量映射，生成 `bg-bg-primary` `text-text-secondary` 等工具类
    - 字体变量映射，生成 `font-display` `font-body` `font-mono`
  - 参考：`design.md` 第 8.3 节、`/resume-agent-workspace/colors_and_type.css`
- [x] **T5.2** 在 `main.tsx` 中引入 `tokens.css`
  - 确保在 `App.tsx` 之前引入
- [x] **T5.3** 验证令牌生效
  - 写一个临时 `<div className="bg-bg-primary text-text-secondary">` 测试
  - 检查渲染色值：`bg-bg-primary` = `#fafbfc`，`text-text-secondary` = `#475569`
  - 参考：`design.md` 第 8.6 节
- [x] **T5.4** 配置全局基础样式
  - `body` 默认：`bg-bg-primary text-text-primary font-body`
  - `*` 默认：`border-border-default`
  - 滚动条样式（细滚动条，符合设计稿）

---

## 第 6 组：部署脚手架

> 目标：Docker 单容器部署 + Makefile 命令封装 + .env 模板。

- [x] **T6.1** 编写 `Dockerfile`（多阶段构建）
  - Stage 1 `frontend-build`：node:20-alpine，pnpm install + build，产出 `dist/`
  - Stage 2 `runtime`：python:3.11-slim，uv sync，复制 `src` + `static`
  - EXPOSE 5173
  - CMD：`uv run uvicorn resume_agent.main:app --host 0.0.0.0 --port 5173`
  - 参考：`design.md` 第 10.1 节
- [x] **T6.2** 编写 `docker-compose.yml`
  - 单服务 `resume-agent`
  - 端口映射：`5173:5173`
  - 卷挂载：`~/.resume-agent:/root/.resume-agent`
  - 环境变量：LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL（从 .env 读取）
  - restart: unless-stopped
  - 参考：`design.md` 第 10.2 节
- [x] **T6.3** 编写 `Makefile`
  - `install`：`uv sync` + `pnpm install`
  - `dev`：并发启动前端（pnpm dev）+ 后端（uvicorn --reload）
  - `build`：`pnpm build`（前端构建）
  - `test`：`uv run pytest` + `pnpm test`
  - `lint`：`uv run ruff check .` + `uv run mypy src/resume_agent` + `pnpm lint`
  - `typecheck`：`pnpm typecheck`
  - `docker-build`：`docker compose build`
  - `docker-up`：`docker compose up -d`
  - `docker-down`：`docker compose down`
  - `clean`：清理构建产物
- [x] **T6.4** 编写 `.env.example`
  - LLM 配置：LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL
  - Embedding 配置：EMBEDDING_PROVIDER, EMBEDDING_MODEL
  - 存储配置：RESUME_AGENT_HOME, SQLITE_PATH, CHROMA_PATH, FILES_ROOT
  - 服务配置：HOST, PORT, DEBUG, CORS_ORIGINS
  - 每项附注释说明
  - 参考：`design.md` 第 9.1 节
- [x] **T6.5** 更新 `.gitignore`
  - 忽略：`backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`, `~/.resume-agent/`, `.env`, `__pycache__/`, `*.pyc`, `.DS_Store`
- [x] **T6.6** 编写 `README.md`
  - 项目简介（3 行）
  - 快速开始：`git clone` → `cp .env.example .env` → `docker compose up` → 访问 `localhost:5173`
  - 开发模式：`make install` → `make dev`
  - 链接到 `docs/` 详细文档

---

## 第 7 组：前端组件开发

> 目标：实现 workspace 三栏工作台 UI，用静态 mock 数据渲染版本树。

- [x] **T7.1** 实现 `GlobalToolbar` 组件
  - 路径：`components/layout/GlobalToolbar.tsx`
  - 内容：Logo + 版本徽章 / 导航 Tab（简历版本分支、知识库、设置）/ 右侧（状态点 + 本地模式 chip + 头像）
  - 高度：48px（`--header-height`）
  - 配色：`bg-bg-secondary border-b border-border-default`
  - 参考：`/resume-agent-workspace/pages/workspace.html` 第 180-202 行
- [x] **T7.2** 实现 `MainLayout` 组件
  - 路径：`components/layout/MainLayout.tsx`
  - 三栏 flex 布局：左 260px（`--left-panel-width`）/ 中 flex-1 / 右 380px（`--right-panel-width`）
  - 高度：`calc(100vh - 48px)`
  - 接收 props：`left`, `center`, `right`（ReactNode）
- [x] **T7.3** 实现 `LeftPanel` 组件
  - 路径：`components/layout/LeftPanel.tsx`
  - 内容：品牌区 / 导航列表（工作台、版本树、知识库、JD分析、Gap、时间线）/ 上传区（简历 + 知识素材）/ 知识库状态指示器
  - 导航项：图标 + 标签 + 徽章（badge）
  - 上传区：`<UploadZone>` 拖拽区（UI，不接后端）
  - 底部：`<KnowledgeStatus>` 切片数 + 进度条（72%）+ "86 篇切片 · Chroma local"
  - 参考：`workspace.html` 第 209-289 行
- [x] **T7.4** 实现 `CenterPanel` 组件
  - 路径：`components/layout/CenterPanel.tsx`
  - 内容：面包屑栏（master / 安全岗 / tencent-researcher）+ Tab Pills（版本树 / 预览 / Diff）+ React Flow 画布
  - 面包屑用 `<Breadcrumb>` 子组件
  - 画布区域渲染 `<VersionTree>`
  - 参考：`workspace.html` 第 291 行起
- [x] **T7.5** 实现 `VersionTree` 组件（React Flow）
  - 路径：`components/tree/VersionTree.tsx`
  - 使用 `@xyflow/react` 的 `ReactFlow` 组件
  - 注册三种自定义节点类型：master / branch / company
  - 数据来源：`data/mockTree.ts`（静态）
  - 画布配置：可缩放、可拖拽、`fitView`
  - 背景：`Background` variant="dots"
  - 节点连线：`edge` 类型 `smoothstep`
- [x] **T7.6** 实现自定义节点组件
  - `MasterNode`：圆形，`bg-node-master`，`shadow-glow-master`，64x64px
  - `BranchNode`：圆角矩形，`bg-node-branch`，`shadow-glow-secondary`
  - `CompanyNode`：矩形，`bg-node-company`，带公司名标签
  - 每个节点含 `<Handle>` 用于连线
  - 参考：`design.md` 第 7.3 节
- [x] **T7.7** 实现 `RightPanel` 组件
  - 路径：`components/layout/RightPanel.tsx`
  - 内容：JD 分析卡片（空状态）+ Gap 报告列表（空状态）+ AI 生成预览区（空状态）
  - 宽度：380px（`--right-panel-width`）
  - 空状态：提示文案 + 引导图标
- [x] **T7.8** 实现通用子组件
  - `Breadcrumb`：路径面包屑，分隔符 `/`
  - `UploadZone`：拖拽上传区，虚线边框 + 图标 + 标题 + 提示
  - `KnowledgeStatus`：标签 + 进度条 + 详情文案
- [x] **T7.9** 组装 `Workspace` 页面
  - 路径：`routes/Workspace.tsx`
  - 结构：`<GlobalToolbar />` + `<MainLayout left={<LeftPanel/>} center={<CenterPanel/>} right={<RightPanel/>} />`
  - 用 mock 数据填充版本树

---

## 第 8 组：静态数据

> 目标：提供 mock 数据，让前端无需后端即可渲染完整版本树。

- [x] **T8.1** 创建 `frontend/src/data/mockTree.ts`
  - 模拟版本树结构：1 个 master + 2 个 branch（安全、推荐）+ 3 个 company 节点
  - 数据格式对齐 `design.md` 第 5.3 节的 GET /api/tree 响应
  - 含 nodes 数组与 edges 数组
  - 示例结构：
    ```
    master
    ├── security（安全岗方向）
    │   ├── tencent-researcher（Tencent 安全研究员）
    │   └── bytedance-sec（字节跳动 安全）
    └── recommendation（推荐算法方向）
        └── alibaba-rec（阿里 推荐算法）
    ```
- [x] **T8.2** 创建 `frontend/src/data/mockJdAnalysis.ts`
  - 模拟 JD 分析结果：技术栈、硬技能、软技能、加分项
  - 数据格式：
    ```ts
    {
      tech_stack: ["Python", "PyTorch", "Linux"],
      hard_skills: ["模型训练", "分布式系统"],
      soft_skills: ["跨团队协作", "技术文档"],
      bonus: ["顶会论文", "开源贡献"]
    }
    ```
- [x] **T8.3** 创建 `frontend/src/types/tree.ts`
  - 定义 `NodeType = 'master' | 'branch' | 'company'`
  - 定义 `TreeNode` 接口（对齐数据库 schema）
  - 定义 `TreeEdge` 接口
  - 定义 `TreeData` 接口（nodes + edges）

---

## 第 9 组：验证

> 目标：全部质量门禁通过，部署可验证。

### 9.1 前端验证

- [x] **T9.1** 前端 typecheck
  - 命令：`cd frontend && pnpm typecheck`（`tsc --noEmit`）
  - 预期：零错误
- [x] **T9.2** 前端 lint
  - 命令：`cd frontend && pnpm lint`
  - 预期：零错误零警告
- [x] **T9.3** 前端 build
  - 命令：`cd frontend && pnpm build`
  - 预期：成功产出 `frontend/dist/`，含 `index.html` + `assets/`
- [x] **T9.4** 前端视觉验证
  - 命令：`pnpm dev` 后访问 `localhost:5173`
  - 检查：三栏布局可见
  - 检查：版本树画布渲染 mock 数据，三种节点形态配色正确
  - 检查：配色与设计稿 `workspace.html` 视觉一致

### 9.2 后端验证

- [x] **T9.5** 后端 lint
  - 命令：`cd backend && uv run ruff check .`
  - 预期：零错误
- [x] **T9.6** 后端 typecheck
  - 命令：`cd backend && uv run mypy src/resume_agent`
  - 预期：零错误
- [x] **T9.7** 后端 import test
  - 命令：`cd backend && uv run python -c "import resume_agent; print('OK')"`
  - 预期：输出 `OK`，无报错
- [x] **T9.8** 后端单元测试
  - 命令：`cd backend && uv run pytest`
  - 预期：全部通过（含 test_db.py 建表测试 + test_import.py 冒烟测试）
- [x] **T9.9** 后端启动验证
  - 命令：`uv run uvicorn resume_agent.main:app --port 8000`
  - 预期：`GET localhost:8000/api/health` 返回 200 + `db: ready, chroma: ready`
  - 预期：`GET localhost:8000/api/tree` 返回 mock 版本树

### 9.3 Docker 构建测试

- [x] **T9.10** Docker 镜像构建
  - 命令：`docker compose build`
  - 预期：多阶段构建成功，无报错
- [x] **T9.11** Docker 镜像大小检查
  - 命令：`docker images resume-agent-resume-agent`
  - 预期：镜像大小 ≤ 500MB
- [x] **T9.12** Docker 启动测试
  - 命令：`docker compose up -d` → 等待 10s → `curl localhost:5173`
  - 预期：返回前端 `index.html`
  - 预期：`curl localhost:5173/api/health` 返回 200 + ready
- [x] **T9.13** 数据持久化测试
  - 命令：`docker compose down` → `docker compose up -d`
  - 预期：`~/.resume-agent/data.db` 数据保留，master 节点仍在
- [x] **T9.14** 清理测试容器
  - 命令：`docker compose down -v`

### 9.4 文档验证

- [x] **T9.15** 检查 `README.md` 快速开始命令可跑通
- [x] **T9.16** 检查 `docs/architecture.md` 描述与实际架构一致
- [x] **T9.17** 检查 `docs/deployment.md` 部署步骤可执行
- [x] **T9.18** 检查 `docs/configuration.md` 覆盖全部环境变量

---

## 完成标志

以下条件全部满足时，本变更视为完成：

- [x] 第 1 组 全部勾选（环境就绪）
- [x] 第 2 组 全部勾选（后端可启动）
- [x] 第 3 组 全部勾选（数据库就绪）
- [x] 第 4 组 全部勾选（前端可启动）
- [x] 第 5 组 全部勾选（设计令牌生效）
- [x] 第 6 组 全部勾选（部署脚手架就绪）
- [x] 第 7 组 全部勾选（组件渲染完整）
- [x] 第 8 组 全部勾选（mock 数据就绪）
- [x] 第 9 组 全部勾选（验证通过）

**总计：62 项任务**

---

## 后续变更预告

本变更完成后，以下功能变更将依次进入开发：

| 变更 ID | 功能 | 依赖本变更的产出 |
|---------|------|----------------|
| `resume-upload` | 资产冷启动（A2） | upload_records 表、upload 端点、UploadZone 组件 |
| `version-tree` | 版本树管理（B1） | resume_versions 表、tree 端点、VersionTree 组件 |
| `rag-index` | 知识库 RAG（A3+A4） | knowledge_chunks 表、Chroma 集合、embeddings 骨架 |
| `jd-analyze` | JD 分析（C1） | jd 端点、RightPanel JD 卡片 |
| `gap-report` | Gap 报告（C2） | gap 端点、RightPanel Gap 列表 |
| `ai-generate` | AI 生成（B3） | agents/ 目录骨架、generate 端点 |
| `pdf-export` | PDF 导出（B4） | export 端点、CenterPanel 预览区 |
