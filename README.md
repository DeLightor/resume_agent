# Resume-Agent

把简历当代码仓库来管：Git 式版本树 + RAG 知识库 + AI 动态生成。

技术求职者手里从来不是「一份简历」，而是十几份针对不同公司、不同方向裁剪过的版本。Resume-Agent 用 Git 的方式管理这整片「简历森林」——Master 主干分化方向分支，分支长出公司专属节点，改一次主干所有子分支自动继承。

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
git clone https://github.com/DeLightor/resume_agent.git
cd resume_agent
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY 和 MINERU_API_TOKEN
docker compose up
```

访问 http://localhost:5173

### 方式二：源码开发

```bash
git clone https://github.com/DeLightor/resume_agent.git
cd resume_agent
make install    # 安装前后端依赖（需要 uv + pnpm）
make dev        # 启动开发服务器
```

- 前端：http://localhost:5173
- API：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 前置要求

| 工具 | 版本 | macOS / Linux | Windows |
|------|------|---------------|---------|
| Node.js | ≥ 20 | [nodejs.org](https://nodejs.org/) | [nodejs.org](https://nodejs.org/) |
| pnpm | ≥ 9 | `npm install -g pnpm` | `npm install -g pnpm` |
| Python | ≥ 3.10 | [python.org](https://python.org/) | [python.org](https://python.org/) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Docker | ≥ 24（可选） | [docker.com](https://docker.com/) | [docker.com](https://docker.com/) |

## 快速安装

### macOS / Linux

```bash
./install.sh
```

脚本会自动检测环境、安装依赖、引导配置 LLM API Key 和 MinerU Token。

### Windows

```powershell
# 一键安装（检测环境 + 安装依赖 + 配置 LLM + MinerU）
powershell -ExecutionPolicy Bypass -File install.ps1

# 日常开发命令
powershell -ExecutionPolicy Bypass -File Makefile.ps1 dev        # 启动开发服务器
powershell -ExecutionPolicy Bypass -File Makefile.ps1 test       # 运行测试
powershell -ExecutionPolicy Bypass -File Makefile.ps1 build      # 构建前端
powershell -ExecutionPolicy Bypass -File Makefile.ps1 install     # 安装依赖
powershell -ExecutionPolicy Bypass -File Makefile.ps1 clean       # 清理构建产物
```

> **注意**：Windows 上不要直接 `.\Makefile.ps1 dev`，会被记事本打开。必须用 `powershell -ExecutionPolicy Bypass -File` 执行。

Windows 数据存储路径：`%USERPROFILE%\.resume-agent\`（自动创建）

### Docker 一键启动（无需上述依赖）

```bash
docker compose up
```

访问 `http://localhost:5173` 即可使用。

## 配置

复制 `.env.example` 为 `.env` 并填入以下配置（或运行安装脚本自动引导）：

### LLM 配置（必需）

```bash
LLM_PROVIDER=deepseek              # openai / deepseek / custom
LLM_API_KEY=sk-xxxxxxxx             # API Key
LLM_BASE_URL=https://api.deepseek.com  # OpenAI 兼容端点（不带 /v1）
LLM_MODEL=deepseek-v4-pro           # 模型名
```

支持任何 OpenAI 协议兼容的 LLM 服务（DeepSeek、OpenAI、Moonshot、本地 Ollama 等）。

### MinerU 配置（简历解析必需）

```bash
MINERU_API_TOKEN=                   # 在 https://mineru.net/apiManage 获取
MINERU_API_BASE=https://mineru.net
```

MinerU 提供云端文档解析 API，用于简历上传解析和 JD 截图 OCR。有免费额度，无需自建部署。

### Tavily 配置（AI 导师学习建议，可选）

```bash
TAVILY_API_KEY=tvly-dev-xxxxxxxx     # 在 https://tavily.com 获取
```

Tavily 提供 Web 搜索 API，用于 AI 导师为技能缺口推荐真实有效的学习资源链接。有免费额度（1000 次/月）。`tavily-python` 已纳入 `pyproject.toml` 依赖，`uv sync` 自动安装。未配置 API Key 时降级为 LLM 训练数据生成的链接。

### Embedding 配置

知识库向量检索使用 Chroma 内置的 `all-MiniLM-L6-v2` 本地模型，无需额外配置 API Key，开箱即用。

### 数据存储

```bash
RESUME_AGENT_HOME=~/.resume-agent
SQLITE_PATH=~/.resume-agent/data.db
CHROMA_PATH=~/.resume-agent/chroma
FILES_ROOT=~/.resume-agent/files
```

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + Vite + TypeScript + Tailwind CSS v4 + React Flow v12 |
| 后端 | Python 3.10+ + FastAPI + uvicorn |
| 数据库 | SQLite（元数据）+ Chroma（向量库，嵌入式，all-MiniLM-L6-v2） |
| LLM | DeepSeek / OpenAI 兼容协议（结构化提取、反思审核、简历生成、导师建议） |
| OCR | MinerU 云端 API（JD 截图解析，支持 PDF/图片/DOCX） |
| Web 搜索 | Tavily API（AI 导师学习资源搜索，真实 URL） |
| PDF | reportlab（ATS 友好，文本可选可解析，CJK 字体支持，多模板） |
| 部署 | Docker Compose 单容器 |

## 功能概览

### v1.0 MVP 核心功能

| 功能 | 说明 |
|------|------|
| 版本树管理 | Git 式树状画布，主干 → 方向分支 → 公司节点 |
| 知识库 RAG | 上传文档 → 自动分块 → 向量索引 → 语义检索 |
| JD 截图分析 | 多文件上传（截图/PDF/TXT）→ MinerU OCR → LLM 结构化提取 → 自动去重 |
| 技能 Gap 报告 | JD 技能 vs 知识库 → 向量相似度三色判定（已覆盖/部分缺口/未涉及） |
| AI 简历生成 | 检索 → 反思审核 → 撰写润色（3 步工作流，不依赖 LangGraph） |
| PDF 导出 | ATS 友好模板，文本可选可解析，支持中文 |

### v1.1 增强功能

| 功能 | 说明 |
|------|------|
| 简历预览与模板 | 3 套内置模板（modern/classic/tech），实时预览，模板选择器 |
| AI 智能补全 | Gap 报告驱动，建议卡片，逐条采纳，分段缓存 |
| 版本 Diff 对比 | 字段级 diff（experience/projects/skills），结构化卡片渲染，新增/删除/修改高亮 |
| AI 导师学习建议 | Tavily Web 搜索 + 并行 LLM 调用，学习路径（概念→实践→验证）+ 真实资源链接 + 状态标记 |

### v1.2 简历精调与模板

| 功能 | 说明 |
|------|------|
| 个人信息管理 | 左栏知识库表单，联系方式/教育背景/自我评价，节点继承，知识库提取 |
| 段落可排序 | 拖拽调整 8 段落顺序，显示/隐藏切换，实时预览刷新 |
| 一键生成整份简历 | asyncio.gather 并行生成，JD 驱动，单段可重生成 |
| 信息完整性检测 | 0-100 评分 + 8 项检查清单，缺失字段高亮，可编辑预览（内联编辑 + 增删条目） |
| 6 套模板系统 | modern/classic/tech/minimal/暖橙卡片风/academic，配置化 TemplateConfig，半透明圆角背景框 |

### v1.3 上游变更与跨平台

| 功能 | 说明 |
|------|------|
| 上游变更检测 | 修改 master 个人信息后，子节点自动标记橙色徽标，提示有变更待合并 |
| 选择性合并 Diff | 逐字段 diff 渲染（中文字段名 + 旧值删除线 → 新值高亮），逐条接受/拒绝或全部接受 |
| 一键安装脚本 | macOS/Linux `install.sh` + Windows `install.ps1`，环境检测 + 依赖安装 + LLM/MinerU 配置引导 |
| Windows 原生支持 | `Makefile.ps1` 等效 Makefile（dev/build/test/lint/clean），PowerShell 跨平台脚本 |

### v1.4 UI 精简与视觉增强

| 功能 | 说明 |
|------|------|
| 导航精简与联动 | 3 项导航 + 动态 badge + GlobalToolbar 统一联动 + "简历版本分支"收起右栏扩大中栏空间 |
| 底部生成联动 | 点击"为该岗位动态生成"自动跳转编辑器，检测 JD 状态，无 JD 自动展开右栏 |
| 节点位置持久化 | 拖拽位置存入 localStorage（版本前缀 key），刷新后保持，一键重置布局 |
| 简历个人头像 | 默认字母头像 + 上传替换（canvas 裁剪），6 套模板渲染 + PDF 导出，≤10MB |
| 节点 hover tooltip | 悬停 500ms 显示名称/类型/完整度/上游变更/时间，createPortal 绕过 React Flow transform |
| 色彩增强与动画 | 品牌色加深（#1d4ed8/#6d28d9）+ 渐变 + 3 入场动画 + 5 交互微动画 + prefers-reduced-motion |

## 项目结构

```
resume-agent/
├── backend/              # Python 后端
│   ├── src/resume_agent/
│   │   ├── api/          # FastAPI 路由（tree/knowledge/jd/gap_report/generate/export/diff/suggest/tutor/templates/completeness/upstream）
│   │   ├── db/           # SQLite + 建表脚本
│   │   ├── rag/          # Chroma 向量库 + 文本分块
│   │   ├── parsers/      # MinerU 文档解析客户端
│   │   ├── llm/          # 统一 LLM 客户端（OpenAI/DeepSeek，支持 tool use）
│   │   ├── tools/        # 外部工具（Tavily Web 搜索）
│   │   ├── export/       # PDF 生成（reportlab，多模板）
│   │   ├── config.py     # 环境变量配置
│   │   └── main.py       # FastAPI 入口
│   └── tests/            # pytest 测试（75+ tests）
├── frontend/             # React 前端
│   ├── src/
│   │   ├── components/   # 组件（layout/tree/knowledge/jd/gap/generate/diff/tutor/template）
│   │   ├── lib/          # API 封装
│   │   ├── styles/       # 设计令牌 + Tailwind
│   │   └── types/        # TypeScript 类型
│   └── vite.config.ts
├── openspec/             # 规格文档
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── Makefile.ps1          # Windows PowerShell Makefile
├── install.sh            # macOS/Linux 安装脚本
├── install.ps1           # Windows 安装脚本
└── .env.example
```

## 开发命令

### macOS / Linux

```bash
make install    # 安装依赖
make dev        # 启动开发服务器（前后端热更新）
make build      # 构建前端
make test       # 运行测试
make lint       # 代码检查
make docker-build  # Docker 构建
make docker-up     # Docker 启动
```

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File Makefile.ps1 dev
powershell -ExecutionPolicy Bypass -File Makefile.ps1 test
powershell -ExecutionPolicy Bypass -File Makefile.ps1 build
```

## 数据存储

所有数据默认存储在 `~/.resume-agent/`（Windows 为 `%USERPROFILE%\.resume-agent\`）：

```
~/.resume-agent/
├── data.db          # SQLite 元数据（版本树、上传记录）
├── chroma/          # Chroma 向量索引（all-MiniLM-L6-v2）
└── files/           # 上传的原始文件 + 导出的 PDF
```

## Windows 常见问题

<details>
<summary>Q: 运行 <code>.\Makefile.ps1 dev</code> 弹出了记事本</summary>

Windows 默认用记事本打开 `.ps1` 文件。必须用 `powershell -ExecutionPolicy Bypass -File` 执行：

```powershell
powershell -ExecutionPolicy Bypass -File Makefile.ps1 dev
```
</details>

<details>
<summary>Q: <code>pnpm install</code> 报 <code>packages field missing</code></summary>

确保 `frontend/` 目录下没有 `pnpm-workspace.yaml` 文件。如果存在，删除它：

```powershell
del frontend\pnpm-workspace.yaml
```
</details>

<details>
<summary>Q: 后端启动正常，但前端显示"LLM 未配置"</summary>

后端从项目根目录读取 `.env` 文件。确保 `.env` 在项目根目录（不是 `backend/` 目录），且 `LLM_API_KEY` 有值：

```powershell
# 查看 .env 内容
cat .env

# 如果缺失，重新运行安装脚本
powershell -ExecutionPolicy Bypass -File install.ps1
```
</details>

<details>
<summary>Q: Docker 显示已安装但报错</summary>

Docker Desktop 未运行。启动 Docker Desktop 后重试，或忽略此警告（不影响本地开发）。
</details>

## License

MIT
