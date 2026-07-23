# 变更提案：project-scaffold

> **变更 ID**：project-scaffold
> **类型**：新增（Added）
> **状态**：proposed
> **提出日期**：2026-07-04
> **目标版本**：v0.1.0-mvp
> **关联 PRD**：`/PRD.md`（Resume-Agent 产品需求文档 v1.0）

---

## 1. 变更摘要

本提案旨在为 Resume-Agent 项目搭建一套**可运行、可部署、可测试**的工程骨架，为后续 MVP 六项核心功能（资产冷启动、版本树、知识库 RAG、JD 分析、Gap 报告、AI 生成、PDF 导出）的开发提供基础底座。

当前仓库仅包含设计稿（`resume-agent-workspace/`）与 PRD，尚无任何可运行代码。本变更将完成从「设计稿」到「可 `docker compose up` 启动的空状态工作台」的跨越。

---

## 2. 变更类型

**新增（Added）** —— 全部为新建文件与目录，不修改既有设计稿。

---

## 3. 变更范围

| 范围模块 | 内容 | 产出物 |
|---------|------|--------|
| 工程骨架初始化 | 前后端目录结构、依赖管理、Makefile | `backend/` `frontend/` `Makefile` `.env.example` |
| 数据库 schema | SQLite 三张核心表 + 初始化脚本 | `backend/src/resume_agent/db/schema.sql` |
| 部署脚手架 | 多阶段 Dockerfile + Compose | `Dockerfile` `docker-compose.yml` |
| 设计令牌迁移 | CSS 变量迁移至 Tailwind v4 体系 | `frontend/src/styles/tokens.css` |
| 第一个页面 | workspace 三栏工作台（静态数据） | 前端路由 + 组件树 |

**不在本变更范围（明确排除）：**

- 简历解析器实现（属 `resume-upload` 变更）
- Chroma 向量检索逻辑（属 `rag-index` 变更）
- LangGraph Agent 工作流（属 `ai-generate` 变更）
- JD 多模态提取（属 `jd-analyze` 变更）
- PDF 导出实现（属 `pdf-export` 变更）

> 本变更只搭骨架与「壳」，不实现任何业务逻辑；所有 API 端点先返回桩数据，前端用静态 mock 渲染版本树。

---

## 4. 动机

### 4.1 为什么需要这个变更

Resume-Agent 的 MVP 包含 6 项交织的核心功能，若直接进入单功能开发，会面临三个问题：

1. **地基缺失**：没有统一的目录结构、依赖锁定、配置注入机制，每个功能各自为政，后期合并冲突频发。
2. **部署不可验证**：PRD 的硬指标是「clone 到可用 ≤15 分钟」，没有 Dockerfile 与 Compose，无法在 CI 中验证这一指标。
3. **设计稿与代码脱节**：`colors_and_type.css` 定义了完整的令牌系统，但没有任何代码消费它，设计变更无法回流到产品。

### 4.2 解决的问题

本变更建立后，将具备以下能力：

- **一键启动**：`docker compose up` 后访问 `localhost:5173`，看到空状态工作台（三栏布局 + 面包屑 + 上传区）。
- **双栈并行开发**：`make dev` 同时启动 Vite 热更新前端与 uvicorn 后端，前端 `localhost:5173`，API 代理到 `:5173/api`。
- **数据落盘**：SQLite 自动建表，Chroma 嵌入式初始化并落盘到 `~/.resume-agent/chroma/`。
- **设计一致性**：设计令牌通过 Tailwind `@theme` 注入，组件直接用 `bg-bg-primary` `text-text-secondary` 等语义类名消费。
- **质量门禁**：`make lint` `make test` `make typecheck` 三件套就绪，CI 可挂载。

### 4.3 与 MVP 路线图的关系

本变更是 MVP 路线图的**第 0 步**，为后续 6 个功能变更提供依赖入口：

```
project-scaffold（本变更）
   ├── resume-upload（资产冷启动 A2）
   ├── version-tree（版本树 B1）
   ├── rag-index（知识库 RAG A3+A4）
   ├── jd-analyze（JD 分析 C1）
   ├── gap-report（Gap 报告 C2）
   └── ai-generate + pdf-export（B3+B4）
```

---

## 5. 验收标准

本变更完成时，必须满足以下全部条件：

### 5.1 工程可运行

- [x] `make install` 在 macOS / Ubuntu 上无报错完成依赖安装
- [x] `make dev` 启动后 `localhost:5173` 返回 workspace 页面（HTTP 200）
- [x] `docker compose up` 一键启动后，5173 端口可访问前端
- [x] Docker 镜像大小 ≤ 500MB（多阶段构建剔除构建依赖）

### 5.2 数据库就绪

- [x] SQLite 在 `~/.resume-agent/data.db` 自动创建
- [x] `resume_versions` `knowledge_chunks` `upload_records` 三张表存在且 schema 正确
- [x] Chroma 在 `~/.resume-agent/chroma/` 完成嵌入式初始化，无独立 server 进程

### 5.3 前端可渲染

- [x] workspace 页面三栏布局可见（GlobalToolbar + LeftPanel + CenterPanel + RightPanel）
- [x] 静态 mock 版本树在 React Flow 画布中渲染（master / 分支 / 公司 三种节点形态）
- [x] 设计令牌生效：背景色、文字色、节点配色与 `colors_and_type.css` 一致

### 5.4 质量门禁

- [x] `pnpm typecheck` 零错误
- [x] `pnpm build` 成功产出 `dist/`
- [x] `uv run ruff check .` 零错误
- [x] `uv run mypy src/resume_agent` 零错误
- [x] 后端 import test 通过：`python -c "import resume_agent"` 无报错

### 5.5 配置与文档

- [x] `.env.example` 列出全部环境变量及说明
- [x] `README.md` 包含 5 行命令的快速开始
- [x] `docs/architecture.md` 描述单容器部署架构

---

## 6. 影响分析

### 6.1 受影响的代码

- **新增**：`backend/` `frontend/` `Dockerfile` `docker-compose.yml` `Makefile` `.env.example` `docs/`
- **保留不动**：`resume-agent-workspace/`（设计稿，作为视觉参照源）、`PRD.md`
- **迁移**：`colors_and_type.css` 中的令牌值复制到 `frontend/src/styles/tokens.css`，原文件保留

### 6.2 受影响的依赖

新增以下核心依赖（在 `pyproject.toml` 与 `package.json` 中声明）：

**Python（pyproject.toml）：**
- fastapi, uvicorn[standard]
- chromadb, langchain, langgraph
- pymupdf, python-docx
- pydantic, pydantic-settings
- sqlalchemy（SQLite ORM，可选）

**Node（package.json）：**
- react, react-dom, react-router-dom
- @xyflow/react（React Flow v12）
- tailwindcss@4, @tailwindcss/vite
- typescript, vite, @vitejs/plugin-react
- vitest, @testing-library/react, playwright

### 6.3 受影响的用户

- **开发者**：首次获得可运行的开发环境
- **最终用户**：尚无影响（功能未实现，仅空壳页面）

---

## 7. 回滚方案

本变更为纯新增，回滚操作安全且无副作用。

### 7.1 回滚步骤

1. **删除新增目录与文件**：
   ```bash
   rm -rf backend/ frontend/ docs/
   rm -f Dockerfile docker-compose.yml Makefile .env.example
   rm -rf openspec/changes/project-scaffold/
   ```

2. **恢复设计稿原状**：设计稿目录 `resume-agent-workspace/` 全程未被修改，无需恢复。

3. **清理本地数据卷**（可选，仅当已运行过 `docker compose up`）：
   ```bash
   docker compose down -v
   rm -rf ~/.resume-agent
   ```

4. **验证回滚结果**：仓库应恢复到仅包含 `PRD.md`、`resume-agent-workspace/`、`.gitignore` 的状态。

### 7.2 回滚验证

回滚后执行以下检查确认状态：

- [x] `git status` 显示工作区干净（无残留新增文件）
- [x] `resume-agent-workspace/colors_and_type.css` 内容未变
- [x] `resume-agent-workspace/pages/workspace.html` 内容未变
- [x] `PRD.md` 内容未变

### 7.3 回滚风险评估

- **风险等级**：低
- **原因**：本变更不修改任何既有文件，回滚等同于「删除新增」，无合并冲突风险。
- **数据影响**：若已运行过容器，`~/.resume-agent/` 下可能残留空数据库与空 Chroma 索引，删除即可，无业务数据丢失风险。

---

## 8. 实施路径

本变更按以下顺序推进，详细任务见 `tasks.md`：

1. **工具链检查** → 确认 uv / node / pnpm 版本满足要求
2. **后端骨架** → pyproject.toml + src 结构 + config + main
3. **数据库初始化** → SQLite schema 脚本 + Chroma PersistentClient
4. **前端骨架** → Vite + React + TS + Tailwind v4 + 路由
5. **设计令牌迁移** → tokens.css + Tailwind @theme
6. **部署脚手架** → Dockerfile 多阶段 + Compose + Makefile + .env.example
7. **前端组件开发** → GlobalToolbar / MainLayout / LeftPanel / CenterPanel / RightPanel
8. **静态数据** → mock 版本树 + mock JD 分析
9. **验证** → typecheck + build + lint + import test + Docker 构建测试

---

## 9. 开放问题

以下问题在实施过程中需要进一步确认，但不阻塞本提案通过：

| # | 问题 | 当前倾向 | 决策时机 |
|---|------|---------|---------|
| 1 | SQLAlchemy ORM 还是原生 sqlite3？ | 倾向原生 sqlite3 + dataclass，减少依赖 | 后端骨架阶段 |
| 2 | React Flow v11 还是 v12（@xyflow/react）？ | 倾向 v12，长期维护 | 前端骨架阶段 |
| 3 | Tailwind v4 是否需要 PostCSS 插件？ | v4 用 @tailwindcss/vite 插件，无需 PostCSS | 令牌迁移阶段 |
| 4 | PDF 预览组件用 react-pdf 还是 iframe？ | 本变更不涉及，留 pdf-export 变更 | — |

---

## 10. 参考资料

- PRD：`/PRD.md`
- 设计稿：`/resume-agent-workspace/pages/workspace.html`
- 设计令牌：`/resume-agent-workspace/colors_and_type.css`
- OpenSpec 配置：`/openspec/config.yaml`
- 技术设计：`./design.md`
- 任务清单：`./tasks.md`
