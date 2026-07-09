# Resume-Agent 产品需求文档（PRD）

> 文档版本：v1.3　|　状态：ACTIVE　|　日期：2026-07-09　|　定位：开源个人简历管理系统

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
| JD 截图结构化提取准确率 | ≥ 80% | 30 张招聘截图提取结果人工评估 |
| AI 生成简历内容可用率 | ≥ 75% | 用户主观评分 ≥ 4/5，套话率 < 15% |
| 端到端生成延迟（含 PDF） | ≤ 30s | 选定岗位到 PDF 产出，P95 |
| 部署到可用时间 | ≤ 15 分钟 | 从 clone 到首次访问工作台 |
| Docker 镜像大小 | ≤ 500MB | 多阶段构建，剔除构建依赖 |

### MVP 完成状态（v1.0 + v1.1 + v1.2 + v1.3）

| 用户故事 | 状态 | 实现方式 |
|----------|------|----------|
| US-1 资产冷启动 | ✅ | PyMuPDF + python-docx 解析，版本树初始化 |
| US-2 版本树管理 | ✅ | React Flow v12 可视化，节点 CRUD，面包屑导航 |
| US-3 知识库 RAG | ✅ | Chroma 嵌入式 + all-MiniLM-L6-v2 本地 Embedding |
| US-4 JD 截图分析 | ✅ | MinerU 云端 OCR + DeepSeek LLM 结构化提取，多文件去重 |
| US-5 技能 Gap 报告 | ✅ | 向量相似度三色判定 + LLM 描述生成 |
| US-6 AI 动态生成 | ✅ | 函数链工作流（检索→反思→撰写），不依赖 LangGraph |
| US-7 PDF 导出 | ✅ | reportlab ATS 模板，STSong-Light CJK 字体 |
| US-8 简历预览与模板 | ✅ | 3 套内置模板（modern/classic/tech），实时预览，模板选择器 |
| US-9 AI 智能补全 | ✅ | Gap 报告驱动，建议卡片，逐条采纳，分段缓存 |
| US-10 版本 Diff 对比 | ✅ | 字段级 diff（experience/projects/skills），结构化卡片渲染 |
| US-11 AI 导师学习建议 | ✅ | Tavily Web 搜索 + 并行 LLM 调用，学习路径 + 资源推荐 + 状态标记 |
| US-12 个人信息管理 | ✅ | 左栏知识库表单，联系方式/教育背景/自我评价，节点继承，知识库提取 |
| US-13 简历段落可排序 | ✅ | 拖拽调整 8 段落顺序，显示/隐藏切换，实时预览刷新 |
| US-14 一键生成整份简历 | ✅ | asyncio.gather 并行生成，JD 驱动，单段可重生成 |
| US-15 信息完整性检测 | ✅ | 0-100 评分 + 8 项检查清单，缺失字段高亮，可编辑预览 |
| US-16 模板系统配置化 | ✅ | 6 套模板（modern/classic/tech/minimal/暖橙卡片风/academic），TemplateConfig |
| US-17 上游变更检测 | ✅ | master 修改后子节点标记橙色徽标，upstream_changes 字段级 diff |
| US-18 选择性合并 Diff | ✅ | 逐字段接受/拒绝按钮，字段级 diff 渲染，全部接受/批量操作 |
| US-19 一键安装脚本 | ✅ | install.sh（macOS/Linux）+ install.ps1（Windows），5 步引导 |
| US-20 Windows 原生支持 | ✅ | Makefile.ps1 PowerShell 等效，路径兼容，.env 多级查找 |

---

## 2. User Experience & Functionality

### User Personas

**P1 — 算法工程师「林」**
- 27 岁，硕士毕业 3 年，同时投递推荐算法、NLP、大模型方向
- 痛点：每个方向要突出不同项目，改简历改到崩溃；优质论文和比赛经历散落多处
- 期望：把所有素材丢进去，按岗位一键生成

**P2 — 网络安全研究员「陈」**
- 25 岁，想从乙方安全公司跳到甲方安全实验室
- 痛点：CVE 编号、CTF 获奖、渗透报告分散，不同公司要求差异大
- 期望：看到 Gap 报告知道该补什么，生成简历不编造经历

**P3 — 后端研发「张」**
- 30 岁，大厂跳槽，投递 5 家不同公司
- 痛点：投递多了记不清每版突出了什么，面试前想对比版本差异
- 期望：版本树可视化 + Diff 对比

### MVP User Stories（v1.0 已完成）

#### US-1~US-7：MVP 核心功能

详见 v1.0 存档。完整链路已打通：上传简历 → 建知识库 → 分析 JD → Gap 报告 → AI 生成 → 导出 PDF。

### v1.1 User Stories

#### US-8：简历预览与模板系统（A5）✅
**As a** 求职者，**I want** 在实时预览中选择简历模板并查看渲染效果，**so that** 我能挑选适合投递的排版风格。

**Acceptance Criteria：**
- [x] 至少 3 套内置模板（现代简约 / 经典学术 / 大厂技术）
- [x] 模板选择器：卡片式预览，点击切换
- [x] 实时预览：编辑内容后预览区即时刷新
- [x] AI 生成内容自动填充到模板对应字段
- [ ] 模板内容可内联编辑（点击文字直接修改）
- [x] PDF 导出与预览一致（所见即所得）
- [x] 模板 JSON Schema 与排版分离（同一数据源，多模板渲染）

#### US-9：AI 智能补全（B6）✅
**As a** 求职者，**I want** AI 根据缺少的内容自动从知识库找素材补全，**so that** 简历不遗漏关键经历。

**Acceptance Criteria：**
- [x] 基于 Gap 报告识别"内容不足"的字段（如某段经历 highlights 只有 1 条）
- [x] 结合 JD 招聘需求和知识库语义检索，主动推荐可补充的素材
- [x] 推荐内容以"建议卡片"形式展示，用户可采纳或忽略
- [x] 采纳后内容写入对应字段，不覆盖已有内容
- [x] 不编造知识库中不存在的内容
- [x] 单次补全建议 ≤ 3 条，避免信息过载

#### US-10：版本 Diff 对比（B5）✅
**As a** 求职者，**I want** 选中两个节点查看差异，**so that** 我能清楚知道每版突出了什么。

**Acceptance Criteria：**
- [x] 选中版本树中任意两节点触发 Diff
- [x] 逐字段对比：新增（绿）/删除（红）/修改（黄）高亮
- [x] 支持 experience / projects / skills 三大段落
- [x] 差异列表可折叠/展开
- [ ] 差异内容可复制到剪贴板

#### US-11：AI 导师学习建议（C3）✅
**As a** 求职者，**I want** 基于 Gap 报告获得学习资源推荐，**so that** 我知道面试前该补什么。

**Acceptance Criteria：**
- [x] 基于 Gap 报告中"未涉及"和"部分缺口"的技能项
- [x] LLM 生成学习路径建议（概念→实践→验证）
- [x] 推荐学习资源类型：文档/课程/开源项目/面试题
- [x] 资源链接可点击跳转
- [x] 学习建议可标记"已掌握/学习中/待开始"状态
- [x] 不承诺资源链接的永久有效性

### v1.2 User Stories

#### US-12：个人信息管理（A1）
**As a** 求职者，**I want** 在知识库中填写和管理个人基础信息，**so that** 简历生成时自动带入联系方式、教育背景等基础数据。

**Acceptance Criteria：**
- [x] 左栏知识库新增"个人信息"表单入口
- [x] 联系方式：姓名、性别、出生年月、电话、邮箱、所在城市、个人网站、GitHub、LinkedIn
- [x] 求职意向：目标岗位、期望薪资（可选）、到岗时间（可选）
- [x] 教育背景（可多条）：学校、学历、专业、时间段
- [x] 自我评价（可选）：一段文字
- [x] 个人信息存入版本树节点的 `content_json.personal_info`
- [x] 子节点创建时自动继承父节点的 `personal_info`
- [x] 支持随时修改个人信息，修改后节点数据更新
- [x] 支持从知识库上传的简历文件中自动提取个人信息
- [x] 字段全面但在简历渲染时按需选用，不强制全部展示

#### US-13：简历段落可排序（A2）
**As a** 求职者，**I want** 拖拽调整简历段落顺序并控制显示/隐藏，**so that** 不同岗位可以突出不同模块。

**Acceptance Criteria：**
- [x] 段落清单：自我评价、工作经历、项目经历、技能总结、教育背景、获奖经历、论文/专利、证书
- [x] 每个段落可独立显示/隐藏
- [x] 段落顺序通过拖拽调整，实时预览即时刷新
- [x] 段落顺序存入节点 `content_json.section_order`
- [x] PDF 导出按排序后的段落顺序渲染
- [x] 子节点继承父节点的 `section_order`

#### US-14：一键生成整份简历（B1）
**As a** 求职者，**I want** 一键生成包含所有段落的完整简历，**so that** 不需要逐段手动生成。

**Acceptance Criteria：**
- [x] 后端 `POST /api/generate/full` 端点
- [x] 并行调用各段落生成（asyncio.gather）：自我评价 AI 生成，其他段落从知识库检索素材
- [x] 有素材的段落生成内容，无素材的段落留空并标注
- [x] 个人信息从节点 `personal_info` 带入，不需要 AI 生成
- [x] 右栏生成区 + 中栏编辑器都有"一键生成"按钮
- [x] 生成完后自动填充到预览区，可逐段精调
- [x] 支持单段重新生成（不影响其他段落）

#### US-15：信息完整性检测（C1）
**As a** 求职者，**I want** 简历生成后自动检测信息完整度，**so that** 我能知道哪些字段缺失或内容不足。

**Acceptance Criteria：**
- [x] 生成后自动扫描关键字段：个人信息是否完整、各段落内容是否稀薄
- [x] 缺失字段在预览区高亮标注（红色：缺失，黄色：内容不足）
- [x] 检测结果以清单形式展示，可点击跳转到对应字段编辑
- [x] 预览区内容可直接点击编辑修改
- [x] 个人信息缺失时提供"从知识库提取"快捷入口
- [x] 完整性评分（0-100）展示在预览区顶部

#### US-16：模板系统配置化（A3）
**As a** 求职者，**I want** 更多模板选择且样式更丰富，**so that** 简历视觉效果更专业。

**Acceptance Criteria：**
- [x] 定义 `TemplateConfig` schema：字体、字号、间距、主题色、栏数、段落配置
- [x] 现有 3 套模板（modern/classic/tech）用配置框架重写
- [x] 新增 3 套模板：极简白（单栏留白）、暖橙卡片风（圆角卡片）、学术风（论文格式）
- [x] 前端模板选择器展示 6 套模板卡片
- [x] 前端预览 + 后端 PDF 渲染统一使用 TemplateConfig
- [x] 模板支持段落顺序配置（与 US-13 联动）

### Non-Goals（v1.3 明确排除）

以下不在 v1.3 范围内：

- **多用户/协作**：仍是单用户本地应用
- **云端同步**：不做跨设备同步
- **投递时间线追踪**：不在 v1.3 内
- **移动端适配**：仅桌面端（≥ 1024px）
- **开源模型本地运行（Ollama）**：继续用云端 LLM API
- **模板市场/自定义模板导入**：v1.3 只提供内置模板
- **ATS 评分**：v1.3 不做自动评分
- **CI Windows 矩阵测试**：手动验证已覆盖，CI 自动化留后续

---

## 3. AI System Requirements

### Tool Requirements

| 组件 | 技术选型 | 用途 | MVP 实际 |
|------|----------|------|----------|
| Agent 工作流 | 函数链（非 LangGraph） | 检索→反思→撰写链路 | ✅ 已实现 |
| 向量库 | Chroma（本地嵌入式） | 简历素材切片存储与语义检索 | ✅ 已实现 |
| 文档解析 | PyMuPDF（PDF）+ python-docx（Word） | 简历原文提取 | ✅ 已实现 |
| OCR | MinerU 云端 API | JD 截图/图片解析为 Markdown | ✅ 已实现 |
| 文本切片 | 自实现 chunker | chunk size 512，overlap 50 | ✅ 已实现 |
| Embedding | all-MiniLM-L6-v2（Chroma 内置） | 向量化，本地运行无需 API | ✅ 已实现 |
| LLM | DeepSeek / OpenAI 兼容协议 | 简历解析、JD 提取、生成、反思 | ✅ 已实现 |
| PDF 生成 | reportlab | ATS 友好 PDF，文本可选，CJK 字体 | ✅ 已实现 |

### Agent 工作流（函数链实现）

```
[输入: 岗位JD + 选定的公司节点]
        │
        ▼
  ┌─────────────┐
  │ 检索         │ ← Chroma 向量检索 Top-K 经历块
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ 反思         │ ← LLM 检测套话/矛盾/夸大，标注可信度
  └──────┬──────┘
         │ （不合格经历被过滤或要求重新检索）
         ▼
  ┌─────────────┐
  │ 撰写         │ ← LLM 按模板拼装、润色
  └──────┬──────┘
         │
         ▼
  [输出: 结构化简历 JSON → PDF]
```

v1.1 扩展：在撰写后新增「补全」节点，基于 Gap 报告主动检索缺失内容的素材。

### v1.1 模板系统架构

```
简历数据 JSON（统一数据源）
    │
    ├── 模板 A: 现代简约（reportlab platypus）
    ├── 模板 B: 经典学术（reportlab platypus）
    └── 模板 C: 大厂技术（reportlab platypus）
    │
    ▼
实时预览（前端 SVG/Canvas 渲染）
    │
    ▼
PDF 导出（reportlab，与预览一致）
```

模板设计原则：
- **数据与排版分离**：同一 JSON 数据，不同模板渲染
- **ATS 友好**：所有模板生成的 PDF 文本可选可解析
- **CJK 支持**：STSong-Light CID 字体
- **无外部字体依赖**：不要求用户安装字体文件

### Evaluation Strategy

| 评估项 | Benchmark | Pass Rate |
|--------|-----------|-----------|
| 简历解析准确率 | 100 份真实简历（含中英文、不同模板） | 字段提取 ≥ 90% |
| 语义检索质量 | 50 条标准查询（标注期望召回的文档） | Precision@5 ≥ 85% |
| JD 提取准确率 | 30 张招聘截图（App/网页/海报） | 字段提取 ≥ 80% |
| 生成内容可用率 | 人工评审 20 份生成简历 | 可用率 ≥ 75%，套话率 < 15% |
| 反思过滤有效性 | 对比「有/无反思」的生成质量 | 套话率降低 ≥ 30% |
| 模板渲染一致性 | 预览 vs PDF 逐像素对比 | 关键区域一致率 ≥ 95% |
| 智能补全采纳率 | 20 次补全建议，用户采纳比例 | ≥ 50% |

---

## 4. Technical Specifications

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     浏览器（前端）                           │
│  React + Vite + TypeScript + Tailwind CSS + React Flow      │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐            │
│  │ 左栏导航  │  │ 中栏版本树    │  │ 右栏分析   │            │
│  │ + 上传区  │  │ + 简历预览   │  │ + Gap报告  │            │
│  │ + 知识库  │  │ + 模板选择   │  │ + AI生成   │            │
│  └─────┬────┘  └──────┬───────┘  └─────┬──────┘            │
│        └──────────────┼─────────────────┘                    │
│                       │ REST API (JSON)                      │
└───────────────────────┼─────────────────────────────────────┘
                        │
┌───────────────────────┼─────────────────────────────────────┐
│              FastAPI 后端（Python）                          │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐          │
│  │ 简历解析API  │  │ RAG检索API │  │ AI生成工作流  │          │
│  │ PyMuPDF/    │  │ Chroma     │  │ (检索→反思→   │          │
│  │ python-docx │  │ all-MiniLM │  │  撰写→补全)   │          │
│  └────────────┘  └────────────┘  └──────────────┘          │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐          │
│  │ MinerU OCR │  │ Gap报告    │  │ PDF导出       │          │
│  │ 云端API     │  │ 向量相似度  │  │ reportlab     │          │
│  └────────────┘  └────────────┘  │ 多模板渲染    │          │
│                                   └──────────────┘          │
│  ┌────────────────────────────────────────────┐             │
│  │ SQLite — 版本树/节点元数据/知识库索引        │             │
│  └────────────────────────────────────────────┘             │
│  ┌────────────────────────────────────────────┐             │
│  │ Chroma — 向量库（all-MiniLM-L6-v2 本地）    │             │
│  └────────────────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────┘
                        │
                        ▼
        云端 LLM API（DeepSeek/OpenAI 兼容）
        云端 OCR API（MinerU）
```

### Integration Points

| 端点 | 方法 | 用途 | 版本 |
|------|------|------|------|
| `/api/resumes/upload` | POST | 上传简历文件（PDF/Word） | v1.0 ✅ |
| `/api/tree` | GET | 获取版本树结构 | v1.0 ✅ |
| `/api/tree/node` | POST | 新建分支/节点 | v1.0 ✅ |
| `/api/knowledge/upload` | POST | 上传知识素材 | v1.0 ✅ |
| `/api/knowledge/search` | POST | 语义检索 | v1.0 ✅ |
| `/api/jd/analyze` | POST | 多文件截图→结构化提取 | v1.0 ✅ |
| `/api/gap-report` | POST | 生成 Gap 报告 | v1.0 ✅ |
| `/api/generate` | POST | AI 生成简历段落 | v1.0 ✅ |
| `/api/export/pdf` | POST | 导出 PDF | v1.0 ✅ |
| `/api/templates` | GET | 获取模板列表 | v1.1 |
| `/api/templates/{id}/preview` | POST | 渲染模板预览 | v1.1 |
| `/api/generate/suggest` | POST | AI 智能补全建议 | v1.1 |
| `/api/tree/diff` | POST | 两节点 Diff 对比 | v1.1 |
| `/api/tutor/suggest` | POST | AI 导师学习建议 | v1.1 ✅ |
| `/api/generate/full` | POST | 一键生成整份简历 | v1.2 |
| `/api/tree/node/{id}/personal-info` | PUT | 更新节点个人信息 | v1.2 |
| `/api/templates` | GET | 获取模板列表（配置化，6 套） | v1.2 |
| `/api/resume/check-completeness` | POST | 信息完整性检测 | v1.2 |
| `/api/tree/node/{id}/upstream-changes` | GET | 获取上游变更列表 | v1.3 ✅ |
| `/api/tree/node/{id}/merge` | POST | 合并指定字段 | v1.3 ✅ |
| `/api/tree/node/{id}/merge/all` | POST | 批量全部接受 | v1.3 ✅ |
| `/api/tree/node/{id}/reject` | POST | 拒绝指定字段 | v1.3 ✅ |

### 数据存储

| 存储 | 内容 | 位置 |
|------|------|------|
| SQLite | 简历版本树结构、节点元数据、上传记录 | 本地 `~/.resume-agent/data.db` |
| Chroma | 简历切片 + 知识素材切片的向量索引 | 本地 `~/.resume-agent/chroma/` |
| 文件系统 | 原始上传文件、生成的 PDF | 本地 `~/.resume-agent/files/` |
| LLM API Key | 用户配置的云端 API Key | 本地 `.env`（不传云端） |

### Security & Privacy

- **本地优先**：所有简历数据、知识库素材存储在用户本地文件系统，不上传到任何云端服务器
- **API Key 安全**：LLM API Key 存储在本地 `.env`，仅后端调用时使用，前端不接触
- **数据脱敏**：调用 LLM API 时传输的内容为简历文本（用户知情），不包含用户身份信息
- **无追踪**：不植入 analytics、不打点、不上报使用数据
- **开源透明**：代码开源，用户可审计数据处理流程

### 开源部署与分发

本项目面向开源社区，部署便捷性是核心体验。用户应能在 **15 分钟内** 从 clone 到可用。

#### 部署方式

| 方式 | 目标用户 | 命令 | 状态 |
|------|----------|------|------|
| **Docker Compose** | 有 Docker 环境的用户 | `docker compose up` | ✅ v1.0 |
| **源码 + Makefile** | 想改代码的开发者 | `make install && make dev` | ✅ v1.0 |
| **一键脚本** | 不想装 Docker 的用户 | `./install.sh` 或 `install.ps1` | ✅ v1.3 |

#### 依赖管理

| 语言 | 工具 | 锁文件 | 版本要求 |
|------|------|--------|----------|
| Python | uv | `uv.lock` | Python ≥ 3.10 |
| Node | pnpm | `pnpm-lock.yaml` | Node ≥ 20 |

#### 跨平台支持

| 平台 | 支持状态 | 说明 |
|------|----------|------|
| macOS（Intel + Apple Silicon） | ✅ | 主要开发和测试平台 |
| Linux（Ubuntu 22.04+ / Debian 12+） | ✅ | Docker 方案优先验证 |
| Windows（PowerShell 原生） | ✅ | `install.ps1` + `Makefile.ps1`，无需 WSL |

---

## 5. Risks & Roadmap

### Phased Rollout

| 阶段 | 内容 | 状态 | 预估周期 |
|------|------|------|----------|
| **v1.0 MVP** | US-1~US-7：资产冷启动 + 版本树 + 知识库RAG + JD分析 + Gap报告 + AI生成 + PDF导出 | ✅ 已完成 | 6 周 |
| **v1.1** | US-8~US-11：简历预览/模板 + 智能补全 + 版本Diff + AI导师 | ✅ 已完成 | 4-5 周 |
| **v1.2** | US-12~US-16：个人信息管理 + 段落可排序 + 一键生成 + 信息完整性检测 + 模板配置化 | ✅ 已完成 | 3 周 |
| **v1.3** | US-17~US-20：上游变更检测+选择性合并 + 一键安装脚本 + Windows 原生支持 | ✅ 已完成 | 2 周 |
| **v2.0** | 开源模型本地运行(Ollama) + 模板市场 + 插件系统 + 移动端 | 📋 规划中 | +6 周 |

### Technical Risks

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 简历解析准确率不达标 | 冷启动体验差 | 中 | 多解析器兜底，人工确认机制 |
| LLM 生成套话率高 | 生成内容不可用 | 中 | 反思节点检测 + Prompt 迭代优化，套话率红线 < 15% |
| LLM API 延迟和成本 | 生成太慢/太贵 | 中 | 流式输出 + 缓存检索结果；支持多家 API 切换 |
| 模板预览与 PDF 不一致 | 所见非所得 | 中 | 统一渲染引擎，预览用 reportlab SVG 导出 |
| 智能补全推荐质量低 | 用户忽略建议 | 中 | 基于 Gap 报告精准定位，限制建议数量 ≤ 3 |
| Chroma 大规模性能 | 1000+ 切片检索变慢 | 低 | v1.1 规模（百级）足够，预留 PGVector 方案 |
| React Flow 复杂交互 | Diff 视图渲染卡顿 | 低 | 节点数 ≤ 50 时无压力 |
| MinerU API 可用性 | JD 分析不可用 | 低 | 缓存解析结果，API 宕机时降级为手动输入 |
| 段落拖拽排序兼容性 | 排序交互不流畅 | 低 | 使用成熟库（dnd-kit），限制段落数 ≤ 8 |
| 模板配置化复杂度 | 渲染不一致 | 中 | 前端 CSS + 后端 reportlab 共享 TemplateConfig，集成测试覆盖 |
| 一键生成并发压力 | LLM API 限流 | 中 | 并行调用限 5 路，单路失败不影响整体，失败段落留空标注 |
| 个人信息继承一致性 | 子节点数据不同步 | 低 | 创建时快照继承，修改时不自动传播（v1.3 考虑自动合并） |

### Key Dependencies

- **LLM API 可用性**：核心功能依赖云端 LLM，API 宕机时展示类功能仍可用
- **MinerU API**：JD 截图 OCR 依赖，有免费额度，API 宕机时降级为手动输入 JD
- **Chroma 嵌入式**：向量检索底层依赖，需持续维护稳定性
- **reportlab**：PDF 生成唯一依赖，成熟稳定

### v1.2 → v1.3 变更摘要

- **新增**：US-17 上游变更检测与提示（master 修改后子节点标记橙色徽标）
- **新增**：US-18 选择性合并 Diff 视图（逐字段接受/拒绝，字段级 diff 渲染）
- **新增**：US-19 一键安装脚本（install.sh + install.ps1，环境检测 + 依赖安装 + LLM/MinerU 配置引导）
- **新增**：US-20 Windows 原生支持（Makefile.ps1，路径兼容，.env 多级查找，README FAQ）
- **更新**：API 集成点新增 4 个端点（upstream-changes / merge / merge/all / reject）
- **更新**：跨平台支持表 Windows 从 WSL2 改为原生 PowerShell
- **更新**：Python 版本要求从 3.12 放宽到 3.10
- **更新**：部署方式表一键脚本标记为 ✅ v1.3
- **修复**：后端 .env 读取路径（env_file 改为多级查找 `["../.env", ".env"]`）
- **修复**：pnpm-workspace.yaml 误判问题（删除，改用 package.json onlyBuiltDependencies）

---

## Appendix

### 现有设计稿映射

| 设计稿文件 | 对应功能 | 使用情况 |
|-----------|----------|----------|
| `pages/workspace.html` | 三栏工作台主界面 | ✅ 已实现 |
| `pages/knowledge-base.html` | 知识库管理界面 | ✅ 已实现 |
| `pages/job-analysis.html` | JD 截图分析界面 | ✅ 已实现 |
| `pages/skill-gap.html` | 技能差距分析界面 | ✅ 已实现 |
| `pages/overview.html` | 总览面板（统计+活动+图表） | 📋 v1.2 |
| `pages/timeline.html` | 投递时间线 | 📋 v1.2 |

### 关于「AI 审核经历真实性」的说明

LLM 无法真正验证经历是否客观发生过，只能检测 AI 套话、前后矛盾与夸大表述。「反思节点」应理解为「检测套话与一致性」，避免对用户过度承诺。

### v1.0 → v1.1 变更摘要

- **更新**：技术栈表修正为实际实现（移除 LangGraph/GPT-4o Vision/React-pdf，加入 MinerU/reportlab/函数链）
- **更新**：架构图移除 LangGraph，新增 MinerU OCR + reportlab
- **新增**：US-8 简历预览与模板系统
- **新增**：US-9 AI 智能补全
- **新增**：US-10 版本 Diff 对比
- **新增**：US-11 AI 导师学习建议
- **更新**：路线图标记 v1.0 已完成
- **更新**：风险表移除 LangGraph 相关风险，新增模板/补全相关风险

### v1.1 → v1.2 变更摘要

- **新增**：US-12 个人信息管理（左栏知识库表单，节点继承，知识库提取）
- **新增**：US-13 简历段落可排序（拖拽排序，显示/隐藏，8 段落清单）
- **新增**：US-14 一键生成整份简历（并行生成，完整段落，单段可重生成）
- **新增**：US-15 信息完整性检测（生成后扫描，高亮标注，完整性评分）
- **新增**：US-16 模板系统配置化（TemplateConfig schema，重写现有 + 新增 3 套）
- **更新**：路线图新增 v1.2（US-12~US-16），原 v1.2 内容移至 v1.3
- **更新**：API 集成点新增 4 个端点

---

## v1.3 Product Requirements

### Executive Summary

**Problem**: v1.2 中个人信息和段落顺序在子节点创建时快照继承，master 修改后不会自动传播。用户需要手动逐个更新子节点，容易遗漏。同时项目缺少一键安装和 Windows 支持，上手门槛高。

**Solution**: 实现 Git 式的"上游变更提示 + 选择性合并"机制，master 修改后子节点标记"有更新可合并"，用户在 Diff 视图逐字段接受/拒绝。同时提供一键安装脚本和 Windows 原生支持。

**Success Criteria**:
- master 修改 personal_info 后，所有子节点在 3 秒内标记"有更新可合并"
- 用户可在 Diff 视图逐字段接受/拒绝变更，接受后子节点数据更新
- 一键安装脚本在 macOS/Linux/Windows 上 5 分钟内完成环境搭建
- Windows PowerShell 原生支持所有开发命令

### User Stories

#### US-17：上游变更检测与提示（B2）✅
**As a** 求职者，**I want** master 节点修改个人信息后，子分支自动标记"有更新可合并"，**so that** 我不会遗漏上游的变更。

**Acceptance Criteria：**
- [x] master 节点修改 personal_info 后，所有子节点标记 `has_upstream_update: true`
- [x] 版本树画布中，有上游更新的节点显示橙色徽标
- [x] 点击节点时，侧栏显示"上游有 N 项变更可合并"提示
- [x] 变更检测范围：仅 personal_info（字段级）
- [x] 合并粒度：字段级（如 contact.name 整体接受/拒绝，不拆到子字段）
- [x] 变更记录存入节点的 `upstream_changes` 字段

#### US-18：选择性合并 Diff 视图（B2）✅
**As a** 求职者，**I want** 在 Diff 视图中逐字段接受或拒绝上游变更，**so that** 子节点的定制修改不会被覆盖。

**Acceptance Criteria：**
- [x] 点击"有更新可合并"提示，打开 Diff 视图
- [x] Diff 视图以字段为单位展示：旧值 → 新值，接受/拒绝按钮
- [x] 支持的字段：personal_info.contact（name/phone/email 等）、personal_info.education、personal_info.summary
- [x] 接受后子节点对应字段更新为 master 的值
- [x] 拒绝后子节点保持原值，标记为"已忽略"
- [x] 全部处理完后，`has_upstream_update` 标记清除
- [x] 支持批量"全部接受"

#### US-19：一键安装脚本（D1）✅
**As a** 新用户，**I want** 一键安装脚本自动检测环境、安装依赖、配置 API Key，**so that** 5 分钟内完成项目搭建。

**Acceptance Criteria：**
- [x] 提供 `install.sh`（macOS/Linux）和 `install.ps1`（Windows PowerShell）
- [x] 自动检测：Node.js ≥ 20、pnpm ≥ 9、Python ≥ 3.10、uv、Docker（可选）
- [x] 缺失依赖时提示安装命令（不自动安装系统级软件）
- [x] 前后端依赖安装：`pnpm install` + `uv sync`
- [x] 交互式配置引导：LLM_PROVIDER、LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
- [x] 交互式配置引导：MINERU_API_TOKEN
- [x] 自动创建 `.env` 文件（从 `.env.example` 复制）
- [x] 检测 Docker 可用性，提示 `docker compose up` 一键启动
- [x] 安装完成提示访问地址（localhost:5173）

#### US-20：Windows 原生支持（D2）✅
**As a** Windows 用户，**I want** 在 PowerShell 中原生运行所有开发命令，**so that** 不需要 WSL 也能使用 Resume-Agent。

**Acceptance Criteria：**
- [x] 所有 Makefile 命令提供 PowerShell 等效版本（`Makefile.ps1`）
- [x] `install.ps1` 安装脚本完整支持 Windows
- [x] 路径分隔符兼容（`os.path.join` 不硬编码 `/`）
- [x] SQLite 路径默认 `~/.resume-agent/data.db`（Windows 下 `%USERPROFILE%\.resume-agent\`）
- [x] Docker Compose 方式完整支持 Windows Docker Desktop
- [x] README 补充 Windows 安装说明 + 常见问题 FAQ
- [ ] CI 增加 Windows 矩阵测试（可选）

### Technical Specifications

#### 上游变更检测

```
master 节点 personal_info 被修改
    ↓
后端检测：遍历所有子节点（递归）
    ↓
对比 master.personal_info vs child.personal_info
    ↓
有差异 → child.upstream_changes = { field: { old, new } }
         child.has_upstream_update = True
    ↓
前端轮询/刷新时获取标记
    ↓
用户在 Diff 视图逐字段接受/拒绝
```

**API 端点：**
- `GET /api/tree/node/{node_id}/upstream-changes` — 获取上游变更列表
- `POST /api/tree/node/{node_id}/merge` — 合并指定字段
- `POST /api/tree/node/{node_id}/merge/all` — 批量全部接受

**数据库变更：**
- `resume_versions` 表新增 `has_upstream_update BOOLEAN DEFAULT FALSE`
- `resume_versions` 表新增 `upstream_changes TEXT`（JSON）

#### 安装脚本架构

```
install.sh / install.ps1
    ├── 1. 环境检测（node/pnpm/python/uv/docker）
    ├── 2. 依赖安装（pnpm install + uv sync）
    ├── 3. 配置引导（交互式 .env 生成）
    ├── 4. Docker 检测（可选）
    └── 5. 完成提示
```

### Risks

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 上游变更检测性能 | 大量子节点时遍历慢 | 低 | 递归遍历限 ≤ 50 节点，异步处理 |
| 合并冲突复杂度 | 用户困惑 | 中 | 仅支持 personal_info，字段级粒度，不做内容段落合并 |
| Windows 路径兼容 | 部分功能不可用 | 中 | 使用 os.path.join，不硬编码路径分隔符 |
| 安装脚本兼容性 | 不同环境检测失败 | 中 | 分步骤执行，失败时提示手动操作 |
