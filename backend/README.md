# Resume-Agent Backend v2.0

Resume-Agent v2.0 后端，基于 FastAPI + SQLite + Chroma + Agent Loop 原生智能体引擎。

## 技术栈

- Python 3.10+ (推荐 3.12)
- FastAPI + uvicorn
- SQLite（原生 sqlite3，支持乐观锁与软删除回收站）
- Chroma（嵌入式 PersistentClient，all-MiniLM-L6-v2 本地向量模型）
- Agent Loop（原生工具注册表、SSE 流式、Reviewer 双审、长期记忆）
- pydantic-settings 配置管理

## 快速开始

```bash
# 安装依赖
uv sync

# 启动后端开发服务器（端口 8000）
uv run uvicorn resume_agent.main:app --reload --port 8000

# 运行测试
uv run pytest

# Lint 检查
uv run ruff check src tests
```

## 目录结构

```
src/resume_agent/
├── main.py          # FastAPI 入口 + 静态托管
├── config.py        # 环境变量配置
├── api/             # 路由层（tree/knowledge/jd/gap/generate/export/mining/applications/agent...）
├── agents/          # Agent Loop 智能体引擎、记忆系统与 Reviewer 双审
├── services/        # 核心业务服务（版本树、投递追踪、素材挖掘等）
├── db/              # SQLite 数据库层与 schema 迁移
├── rag/             # Chroma 向量库 + 文本分块
├── parsers/         # 简历解析与置信度评估
└── tools/           # Agent 工具注册与外部集成（Tavily 等）
```

## 数据存储

所有数据默认落在 `~/.resume-agent/`：

- `data.db` — SQLite 元数据
- `chroma/` — Chroma 嵌入式向量库
- `files/` — 上传文件与生成产物
