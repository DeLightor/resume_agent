# Resume-Agent 产品需求文档（PRD）

> 文档版本：v1.0　|　状态：DRAFT　|　日期：2026-07-04　|　定位：开源个人简历管理系统

---

## 1. Executive Summary

### Problem Statement

技术求职者手里从来不是「一份简历」，而是十几份针对不同公司、不同方向裁剪过的版本。多版本之间混乱、难追溯、难复用：基础信息改一次要手动同步十几个文件，最好的项目经历散落各处，最后连「腾讯那版到底突出了什么」都记不清。现有工具要么只管单份排版（Reactive Resume、OpenResume），要么只管单份匹配打分（Teal、Huntr），无人管理这整片「简历森林」的版本演化。

### Proposed Solution

Resume-Agent 把简历当代码仓库来管：Master 主干分化出方向分支，分支长出公司专属节点，改一次主干所有子分支自动继承。基于 RAG 的个人知识库提供智能检索，AI Agent 按 JD 动态生成 1 页 ATS 友好 PDF。React Flow 可视化的 Git 树是产品灵魂一击——目标用户（算法、安全、后端工程师）天天活在 Git 里，把简历当分支管理是他们的母语。

### Success Criteria

| 指标 | 目标值 | 测量方式 |
|------|--------|----------|
| 简历导入解析成功率 | ≥ 90% | 100 份真实 PDF/Word 简历测试集 |
| 知识库语义检索 Precision@5 | ≥ 85% | 50 条标准查询 benchmark |
| JD 截图结构化提取准确率 | ≥ 80% | 多模态 LLM 对 30 张招聘截图提取结果人工评估 |
| AI 生成简历内容可用率 | ≥ 75% | 用户主观评分 ≥ 4/5，套话率 < 15% |
| 端到端生成延迟（含 PDF） | ≤ 30s | 选定岗位到 PDF 产出，P95 |
| 部署到可用时间 | ≤ 15 分钟 | 从 clone 到首次访问工作台，含 Docker 拉取 |
| Docker 镜像大小 | ≤ 500MB | 多阶段构建，剔除构建依赖 |

---

## 2. User Experience & Functionality

### User Personas

**P1 — 算法工程师「林」**
- 27 岁，硕士毕业 3 年，同时投递推荐算法、NLP、大模型方向
- 痛点：每个方向要突出不同项目，改简历改到崩溃；优质论文和比赛经历散在多处
- 期望：把所有素材丢进去，按岗位一键生成

**P2 — 网络安全研究员「陈」**
- 25 岁，想从乙方安全公司跳到甲方安全实验室
- 痛点：CVE 编号、CTF 获奖、渗透报告分散，不同公司要求差异大
- 期望：看到 Gap 报告知道该补什么，生成简历不编造经历

**P3 — 后端研发「张」**
- 30 岁，大厂跳槽，投递 5 家不同公司
- 痛点：投递多了记不清每版突出了什么，面试前想对比版本差异
- 期望：版本树可视化 + Diff 对比

### User Stories & Acceptance Criteria

#### US-1：资产冷启动（A2）
**As a** 求职者，**I want** 拖入多份旧简历自动解析和去重，**so that** 我不用手动整理十几份文件。

**Acceptance Criteria：**
- [x] 支持 PDF 和 Word（.docx）格式拖拽上传
- [x] 自动提取结构化字段：基本信息、教育经历、工作经历、项目经历、技能列表
- [x] 多份简历间智能去重（同一公司同一岗位只保留最新版）
- [x] 生成初始 Git 树：Master 主干 + 自动推断的方向分支
- [x] 解析失败时保留原始文本并标注「需人工确认」
- [ ] 单份简历解析 ≤ 5s（10 页以内）

#### US-2：版本树管理（B1）
**As a** 求职者，**I want** 用 Git 树可视化查看所有简历版本，**so that** 我能清楚知道哪个公司用了哪版。

**Acceptance Criteria：**
- [x] React Flow 渲染可缩放、可拖拽的树状画布
- [x] 三种节点形态区分：主干（圆形/青色）、方向分支（圆角矩形/紫色）、公司节点（矩形/橙色）
- [x] 点击节点进入编辑或预览
- [x] 面包屑显示当前路径（Master → 安全岗 → Tencent-研究员）
- [x] 支持手动新建分支/节点
- [ ] 节点数量 ≤ 50 时画布渲染 ≤ 100ms

#### US-3：知识库 RAG（A3 + A4）
**As a** 求职者，**I want** 上传周报、论文、CTF 报告等素材建立个人知识库，**so that** AI 生成简历时能检索到我的真实经历。

**Acceptance Criteria：**
- [x] 支持 PDF、Word、Markdown、纯文本格式上传
- [x] 文本切片（chunk size 512 tokens，overlap 50）
- [x] 本地向量库（Chroma）存储，支持语义检索
- [x] 左栏底部常驻知识库状态指示器（切片数、索引进度）
- [x] 检索结果附带来源文档标注
- [ ] 索引 100 篇文档 ≤ 60s

#### US-4：JD 截图分析（C1）
**As a** 求职者，**I want** 上传招聘截图自动提取岗位要求，**so that** 我不用逐字阅读 JD 手动整理。

**Acceptance Criteria：**
- [x] 支持 PNG、JPG、PDF、TXT、WEBP、DOC/DOCX 格式多文件上传
- [x] MinerU OCR + DeepSeek LLM 提取结构化字段：技术栈、硬技能、软技能、加分项
- [x] 多文件上传时自动合并去重
- [x] 右栏 JD 卡片展示，支持编辑修正
- [x] 截图提取失败时提示重新上传
- [ ] 单张截图提取 ≤ 10s

#### US-5：技能 Gap 报告（C2）
**As a** 求职者，**I want** 看到岗位要求与个人能力的差距，**so that** 我知道面试前该补什么。

**Acceptance Criteria：**
- [ ] 自动比对 JD 要求与知识库内容
- [ ] 三色状态标记：已覆盖（绿）、部分缺口（黄）、未涉及（红）
- [ ] 每项 Gap 附带具体描述
- [ ] 不编造、不虚构能力（基于知识库实际内容判断）
- [ ] 报告生成 ≤ 5s

#### US-6：AI 动态生成简历（B3）
**As a** 求职者，**I want** 选定岗位后 AI 自动生成 1 页专属简历，**so that** 我不用手动裁剪经历。

**Acceptance Criteria：**
- [ ] LangGraph Agent 工作流：检索 → 反思审核 → 撰写润色
- [ ] 检索知识库中与 JD 相关的经历（Precision@5 ≥ 85%）
- [ ] 反思节点检测套话、前后矛盾、夸大表述（不承诺验证经历真实性）
- [ ] 生成内容控制在 1 页 A4 以内
- [ ] 生成延迟 ≤ 20s（含 LLM 调用）
- [ ] 生成结果可编辑修正

#### US-7：PDF 导出（B4）
**As a** 求职者，**I want** 一键导出 ATS 友好的 PDF，**so that** 我能直接用于投递。

**Acceptance Criteria：**
- [ ] 至少 1 套 ATS 友好模板（经典学术 / 大厂技术 / 极简风，MVP 至少 1 套）
- [ ] JSON-to-Resume 数据与排版分离
- [ ] PDF 文本可选、可解析（通过 ATS 系统解析测试）
- [ ] 导出延迟 ≤ 3s
- [ ] PDF 预览区实时同步

### Non-Goals

以下明确不在 MVP 范围内，保护时间线：

- **多用户/协作**：MVP 是单用户本地应用，不做账号体系和权限管理
- **云端同步**：不做跨设备同步，所有数据存本地
- **版本对比 Diff 视图（B5）**：MVP 只做版本树展示，不做 Diff 详情对比
- **上游继承自动合并（B2）**：MVP 手动新建分支，不实现 Master 修改自动传播
- **AI 导师学习建议（C3）**：MVP 只做 Gap 报告，不做学习资源推荐
- **投递时间线追踪**：不在 MVP 内
- **移动端适配**：MVP 只做桌面端（≥ 1024px）
- **开源模型本地运行（Ollama）**：MVP 用云端 LLM API，本地模型留后续

---

## 3. AI System Requirements

### Tool Requirements

| 组件 | 技术选型 | 用途 |
|------|----------|------|
| Agent 框架 | LangGraph | 树状 Agent 工作流，支持检索→反思→撰写链路 |
| 向量库 | Chroma（本地） | 简历素材切片存储与语义检索 |
| 文档解析 | PyMuPDF（PDF）+ python-docx（Word） | 简历原文提取 |
| 文本切片 | LangChain TextSplitter | chunk size 512 tokens，overlap 50 |
| Embedding | OpenAI text-embedding-3-small（或 DeepSeek） | 向量化 |
| LLM | GPT-4o / Claude 3.5 Sonnet（用户配置） | 简历解析、JD 提取、生成、反思 |
| 多模态 | GPT-4o Vision | JD 截图 OCR + 结构化提取 |
| PDF 生成 | React-pdf 或 Puppeteer | JSON-to-PDF 渲染 |

### Agent 工作流（LangGraph）

```
[输入: 岗位JD + 选定的公司节点]
        │
        ▼
  ┌─────────────┐
  │ 检索 Agent   │ ← Chroma 向量检索 Top-K 经历块
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ 反思 Agent   │ ← 检测套话/矛盾/夸大，标注可信度
  └──────┬──────┘
         │ （不合格经历被过滤或要求重新检索）
         ▼
  ┌─────────────┐
  │ 撰写 Agent   │ ← 按模板拼装、润色，控制 1 页
  └──────┬──────┘
         │
         ▼
  [输出: 结构化简历 JSON → PDF]
```

### Evaluation Strategy

| 评估项 | Benchmark | Pass Rate |
|--------|-----------|-----------|
| 简历解析准确率 | 100 份真实简历（含中英文、不同模板） | 字段提取 ≥ 90% |
| 语义检索质量 | 50 条标准查询（标注期望召回的文档） | Precision@5 ≥ 85% |
| JD 提取准确率 | 30 张招聘截图（App/网页/海报） | 字段提取 ≥ 80% |
| 生成内容可用率 | 人工评审 20 份生成简历 | 可用率 ≥ 75%，套话率 < 15% |
| 反思过滤有效性 | 对比「有/无反思」的生成质量 | 套话率降低 ≥ 30% |

---

## 4. Technical Specifications

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     浏览器（前端）                           │
│  React + Vite + TypeScript + Tailwind CSS + React Flow      │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐            │
│  │ 左栏导航  │  │ 中栏版本树    │  │ 右栏分析   │            │
│  │ + 上传区  │  │ + PDF预览    │  │ + Gap报告 │            │
│  └─────┬────┘  └──────┬───────┘  └─────┬──────┘            │
│        └──────────────┼─────────────────┘                    │
│                       │ REST API (JSON)                      │
└───────────────────────┼─────────────────────────────────────┘
                        │
┌───────────────────────┼─────────────────────────────────────┐
│              FastAPI 后端（Python）                          │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐          │
│  │ 简历解析API  │  │ RAG检索API │  │ LangGraph    │          │
│  │ PyMuPDF/    │  │ Chroma    │  │ Agent工作流   │          │
│  │ python-docx │  │            │  │ (检索→反思→   │          │
│  │             │  │            │  │  撰写)       │          │
│  └────────────┘  └────────────┘  └──────────────┘          │
│  ┌────────────────────────────────────────────┐             │
│  │ SQLite — 简历版本树/节点元数据/知识库索引    │             │
│  └────────────────────────────────────────────┘             │
│  ┌────────────────────────────────────────────┐             │
│  │ Chroma — 向量库（简历/素材切片）             │             │
│  └────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
              云端 LLM API（OpenAI/Claude/DeepSeek）
```

### Integration Points

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/resumes/upload` | POST | 上传简历文件（PDF/Word） |
| `/api/resumes/parse` | POST | 解析简历→结构化 JSON |
| `/api/tree` | GET | 获取版本树结构 |
| `/api/tree/node` | POST | 新建分支/节点 |
| `/api/knowledge/upload` | POST | 上传知识素材 |
| `/api/knowledge/index` | POST | 触发索引 |
| `/api/knowledge/search` | POST | 语义检索 |
| `/api/jd/analyze` | POST | 上传截图→结构化提取 |
| `/api/gap-report` | POST | 生成 Gap 报告 |
| `/api/generate` | POST | AI 生成简历 |
| `/api/export/pdf` | POST | 导出 PDF |

### 数据存储

| 存储 | 内容 | 位置 |
|------|------|------|
| SQLite | 简历版本树结构、节点元数据、上传记录 | 本地 `~/.resume-agent/data.db` |
| Chroma | 简历切片 + 知识素材切片的向量索引 | 本地 `~/.resume-agent/chroma/` |
| 文件系统 | 原始上传文件、生成的 PDF | 本地 `~/.resume-agent/files/` |
| LLM API Key | 用户配置的云端 API Key | 本地配置文件（不传云端） |

### Security & Privacy

- **本地优先**：所有简历数据、知识库素材存储在用户本地文件系统，不上传到任何云端服务器
- **API Key 安全**：LLM API Key 存储在本地配置文件，仅后端调用时使用，前端不接触
- **数据脱敏**：调用 LLM API 时传输的内容为简历文本（用户知情），不包含用户身份信息
- **无追踪**：不植入 analytics、不打点、不上报使用数据
- **开源透明**：代码开源，用户可审计数据处理流程

### 开源部署与分发

本项目面向开源社区，部署便捷性是核心体验。用户（技术背景求职者）应能在 **15 分钟内** 从 clone 到可用。

#### 部署方式（按优先级）

| 方式 | 目标用户 | 命令 | MVP |
|------|----------|------|-----|
| **Docker Compose** | 有 Docker 环境的用户 | `docker compose up` | ✅ 首选 |
| **源码 + Makefile** | 想改代码的开发者 | `make install && make dev` | ✅ |
| **一键脚本** | 不想装 Docker 的用户 | `curl -fsSL install.sh \| sh` | v0.2 |
| **桌面应用（Tauri）** | 非技术用户 | 下载 .dmg/.AppImage | v1.0 |

#### Docker Compose 部署方案（MVP 首选）

```yaml
# docker-compose.yml（核心结构）
services:
  resume-agent:
    build: .
    ports: ["5173:5173"]        # 前端 + API 同一端口
    volumes:
      - ~/.resume-agent:/root/.resume-agent  # 数据持久化
    environment:
      - LLM_PROVIDER=openai      # 或 claude / deepseek
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_BASE_URL=             # 可选，支持代理/私有部署
```

**关键设计决策：**

1. **单容器部署**：前端 build 后由 FastAPI 静态文件托管，用户只启动 1 个容器、访问 1 个端口（5173）。避免「前端跑 3000、后端跑 8000」的双进程体验。
2. **Chroma 嵌入式模式**：使用 `chromadb` 的 PersistentClient 嵌入式模式，无需单独启动 Chroma server。数据落盘到挂载卷。
3. **数据卷挂载**：`~/.resume-agent` 整个挂载到容器，包含 SQLite、Chroma 索引、上传文件。容器删除数据不丢。
4. **环境变量配置**：所有配置通过环境变量注入，支持 `.env` 文件。无需进入容器改配置。

#### 源码部署方案（开发者）

```bash
# 1. 克隆
git clone https://github.com/<org>/resume-agent.git
cd resume-agent

# 2. 安装依赖（uv 管 Python，pnpm 管 Node）
make install
# 等价于：
#   uv sync                    # Python 依赖（pyproject.toml + uv.lock）
#   pnpm install                # Node 依赖（package.json + pnpm-lock.yaml）

# 3. 配置 LLM
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY

# 4. 启动开发环境（前后端热更新）
make dev
# 前端 http://localhost:5173，API http://localhost:5173/api
```

#### 依赖管理

| 语言 | 工具 | 锁文件 | 版本要求 |
|------|------|--------|----------|
| Python | uv | `uv.lock` | Python ≥ 3.11 |
| Node | pnpm | `pnpm-lock.yaml` | Node ≥ 20 |

- **uv**：比 pip/poetry 快 10-100x，Rust 编写，零配置。锁定全部依赖版本保证可复现。
- **pnpm**：比 npm 快、省磁盘空间，严格锁定。
- **Makefile**：封装常用命令（install / dev / build / test / lint），开发者无需记忆多套工具链。

#### 首次启动引导（Onboarding）

首次访问 `localhost:5173` 时，若检测到未配置 API Key，进入引导流程：

```
步骤 1/3：选择 LLM 提供商
  ○ OpenAI（GPT-4o）
  ○ Anthropic（Claude 3.5 Sonnet）
  ○ DeepSeek
  ○ 自定义（填 Base URL + Key，支持代理/私有部署）

步骤 2/3：输入 API Key
  [________________]  ← 仅存本地，不传任何服务器

步骤 3/3：验证连通性
  → 调用一次轻量 API 测试 Key 有效性
  ✓ 验证通过 / ✗ 请检查 Key

完成 → 进入空状态工作台，左栏提示「拖入旧简历开始」
```

- API Key 写入 `~/.resume-agent/.env`，不进 Git
- 支持后续在「设置」页修改提供商和 Key
- 支持自定义 Base URL（满足用代理、私有部署 LLM 的用户）

#### 跨平台支持

| 平台 | MVP 支持 | 说明 |
|------|----------|------|
| macOS（Intel + Apple Silicon） | ✅ | 主要开发和测试平台 |
| Linux（Ubuntu 22.04+ / Debian 12+） | ✅ | Docker 方案优先验证 |
| Windows（WSL2） | ✅ 通过 WSL2 | 原生 Windows 支持留 v0.2 |
| Windows（原生） | ⚠️ v0.2 | PyMuPDF/Chroma 路径需适配 |

- CI（GitHub Actions）跑 macOS + Ubuntu 双平台测试
- 路径处理统一用 `pathlib`，避免硬编码分隔符

#### 开源仓库结构

```
resume-agent/
├── README.md                    # 快速开始（5 行命令跑起来）
├── docker-compose.yml           # Docker 部署
├── Dockerfile                   # 多阶段构建（前端 build + Python 运行时）
├── Makefile                     # install / dev / build / test / lint
├── .env.example                 # 配置模板
├── CONTRIBUTING.md              # 贡献指南
├── LICENSE                      # MIT 或 Apache 2.0
├── backend/
│   ├── pyproject.toml           # uv 管理依赖
│   ├── uv.lock
│   ├── src/resume_agent/
│   │   ├── main.py              # FastAPI 入口 + 静态文件托管
│   │   ├── api/                 # 路由
│   │   ├── agents/              # LangGraph 工作流
│   │   ├── parsers/             # 简历解析
│   │   ├── rag/                 # Chroma + 检索
│   │   └── config.py            # 环境变量配置
│   └── tests/
├── frontend/
│   ├── package.json             # pnpm 管理依赖
│   ├── pnpm-lock.yaml
│   ├── vite.config.ts
│   └── src/
└── docs/
    ├── deployment.md            # 详细部署文档
    ├── configuration.md         # 配置项说明
    └── architecture.md          # 架构说明
```

#### 开源治理

- **License**：MIT（最宽松，允许商用衍生）
- **CONTRIBUTING.md**：明确开发环境搭建、PR 流程、代码规范
- **Issue 模板**：Bug report + Feature request 模板
- **CI/CD**：GitHub Actions 跑 lint + test，PR 必须通过才能合并
- **Release**：语义化版本（SemVer），每个 Release 附带 Docker 镜像 tag
- **文档**：README 5 行命令跑起来是硬要求，复杂配置留 `docs/`

---

## 5. Risks & Roadmap

### Phased Rollout

| 阶段 | 内容 | 预估周期 |
|------|------|----------|
| **MVP (v0.1)** | 6 项核心功能：资产冷启动 + 版本树 + 知识库RAG + JD分析 + Gap报告 + AI生成 + PDF导出 | 6-8 周 |
| **v0.2** | 上游继承自动合并(B2) + 版本 Diff 对比(B5) + 多模板支持 | +3 周 |
| **v0.3** | AI 导师学习建议(C3) + 投递时间线 + 移动端适配 | +4 周 |
| **v1.0** | 开源模型本地运行(Ollama) + 模板市场 + 插件系统 | +6 周 |

### Technical Risks

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 简历解析准确率不达标 | 冷启动体验差，用户流失 | 中 | 多解析器兜底（PyMuPDF + LLM 辅助），人工确认机制 |
| LangGraph 反思节点效果差 | 生成内容套话率高 | 中 | 设计反思 Prompt benchmark，迭代优化；设置套话率红线 < 15% |
| LLM API 延迟和成本 | 生成简历太慢/太贵 | 中 | 流式输出 + 缓存检索结果；支持多家 API 切换以降本 |
| Chroma 大规模性能 | 1000+ 切片检索变慢 | 低 | MVP 规模（百级）足够，预留切换 PGVector 方案 |
| React Flow 复杂交互 | 拖拽/缩放体验不流畅 | 低 | 节点数 ≤ 50 时无压力；虚拟化渲染留后续 |
| JD 截图多样性格式 | App 截图/海报提取失败率 | 中 | 限制 MVP 支持标准网页截图，复杂格式标注「需人工确认」 |
| Docker 镜像跨平台兼容 | ARM/AMD 架构构建失败 | 中 | Docker buildx 多架构构建，CI 验证 mac/linux 双平台 |
| Python + Node 双栈安装门槛 | 非 Docker 用户环境搭建失败 | 中 | Makefile 封装 + uv/pnpm 自动安装脚本；提供 Docker 规避双栈 |
| Chroma 嵌入式稳定性 | 偶发索引损坏 | 低 | 启动时校验 + 重建索引机制；数据卷备份提示 |

### Key Dependencies

- **LLM API 可用性**：核心功能依赖云端 LLM，API 宕机时生成功能不可用（展示类功能仍可用）
- **PyMuPDF / python-docx**：简历解析的底层依赖，需持续维护兼容性
- **React Flow**：版本树画布的唯一依赖，社区活跃度影响长期可维护性

---

## Appendix

### 现有设计稿映射

| 设计稿文件 | 对应功能 | MVP 使用情况 |
|-----------|----------|-------------|
| `pages/workspace.html` | 三栏工作台主界面 | ✅ 直接参考 |
| `pages/overview.html` | 总览面板（统计+活动+图表） | ❌ 不在 MVP |
| `pages/knowledge-base.html` | 知识库管理界面 | ✅ 参考 |
| `pages/job-analysis.html` | JD 截图分析界面 | ✅ 参考 |
| `pages/skill-gap.html` | 技能差距分析界面 | ✅ 参考 |
| `pages/timeline.html` | 投递时间线 | ❌ 不在 MVP |
| `colors_and_type.css` | 设计令牌系统 | ✅ 直接复用 |

### 关于「AI 审核经历真实性」的说明

需求文档原提到「AI 面试官 Agent 反思审核经历是否真实」。LLM 无法真正验证经历是否客观发生过，只能检测 AI 套话、前后矛盾与夸大表述。PRD 中「反思 Agent」应理解为「检测套话与一致性」，避免对用户过度承诺。
