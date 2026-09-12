# Resume-Agent v2.0 需求文档：Agent 核心化改造

> 文档版本：v2.0　|　状态：已交付（US-27~US-36）　|　日期：2026-09-08　|　最后核对：2026-09-12　|　前置：PRD.md v1.4（US-1~US-26 已交付）

---

## 1. 背景与转型动机

### 1.1 v1.x 现状

v1.0~v1.4 已交付 26 个用户故事（详见 PRD.md）：版本树、知识库 RAG、JD 分析、Gap 报告、AI 生成、模板、Diff、上游合并、跨平台部署全部完成，openspec 已归档 18 个规格。

但架构本质是「**功能堆叠 + 固定函数链**」：

- AI 能力以单次 LLM 调用的形式散落在各 REST 端点里（生成 = 检索→反思→撰写三步固定流水线，见 [generate.py](backend/src/resume_agent/api/generate.py)）
- 用户的每个意图都要自己拆步骤：先传 JD、再选节点、再点生成、再看 Gap、再补全——Agent 不做决策，人做决策
- 全部同步阻塞调用，无 SSE/WebSocket 流式（后端零 streaming 代码），长任务体验是「转圈等待」

### 1.2 为什么转向 Agent 核心

2026 年求职 Agent 领域已被验证的信号：

| 信号 | 来源 | 对本项目的启示 |
|------|------|----------------|
| drafter-reviewer 双 Agent 架构（一个起草、一个用全新上下文批判审查、循环修订） | ai-job-search（GitHub 19.5K stars，年度最快增长的 Claude Code 工作流仓库） | 本项目已有的「反思节点」是雏形，应升级为**独立上下文的 Reviewer Agent** |
| 可见的 Agent 工作流（分数、模型动作、门禁、失败、简历 diff 全部展示在面板上） | AppliedIn 等项目 | 用户要的不是黑盒一键生成，而是**能看到 Agent 在干什么**的过程透明 |
| Human-in-the-loop 默认开启，投递前必须人工批准 | AppliedIn（gated 模式为默认） | Agent 修改简历也应默认走 **diff 预览 → 人工确认**，而非直接覆盖 |
| 诚实性约束是结构性设计而非口号（不编造技能，缺口就显示为缺口） | ai-job-search | 本项目「反思检测套话/不编造知识库外内容」的原则是差异化卖点，v2.0 强化 |
| Agent 记忆随使用增长（记住偏好、薪资预期、越用越懂） | OpenClaw 类产品 | 单用户本地应用天然适合做长期记忆 |

### 1.3 一句话定位

> **开源、本地优先、以 Agent 为核心的「简历森林」管理系统**——竞品没有一个是 Agent-native + 本地优先的。

---

## 2. 目标用户调研

### 2.1 市场格局（2026）

**国际市场**（Rezi / Teal / Huntr / Jobscan / Enhancv 等）：

- 工具分四类：简历构建器、ATS 优化器、求职 CRM、端到端平台，但边界模糊、工作流碎片化
- 用户典型路径是拼装：「Resume.io 里做 → Jobscan 里扫 → Teal 里追踪」，每家都自称 all-in-one
- ATS 解析率是硬指标：Rezi/Teal 单栏模板在 Workday/Greenhouse/Lever/Taleo 四引擎解析率 88%+；双栏模板在 Workday 直接解析失败
- 订阅制怨声载道：周计费悄悄年化、取消后仍扣费是品类级丑闻

**国内市场**（超级简历 WonderCV / 职徒简历 / 100分简历 / AI简历姬）：

- 2026 年超 70% 中大型企业用 ATS 初筛，手动简历通过率不足 20%，针对性优化后可到 70%+
- 模板规模内卷（1000+ 套），但骨架雷同，差异只在配色和区块顺序
- 超级简历的 WonderAI 已上线**对话式简历修改**（2025-2026 新增），验证了国内用户对对话交互的接受度

### 2.2 品类级信任危机（本项目的机会）

第三方实测与媒体记录的 AI 简历工具翻车案例：

- Teal 被记录**把 JD 里的要求（如工作授权）当作用户自己的经历插入简历**
- Rezi 的 AI 弹点生成器会凭空编造「提升收入 47%」这类量化数字
- 2026 年六款主流工具横评结论：**全部六款都会生成虚构的成就数据，无一能验证自己建议的数字**
- 用户最大恐惧：面试时被追问 AI 写的经历，当场露馅

→ **结论：本项目 v1.x 的「反思节点 + 不编造知识库外内容」原则，正好踩中品类最大痛点。v2.0 应把它从流水线里的一个步骤，升级为独立 Reviewer Agent + 结构性诚实约束，并作为产品核心卖点对外表达。**

### 2.3 分人群痛点与 Agent 机会

| 人群 | 核心痛点 | 现有工具的解法 | Agent 核心的更好解法 |
|------|----------|----------------|------------------------|
| 应届生（最大用户群） | 经历少、课程/社团写成流水账、不知道「该写什么」 | 模板 + 案例库参考，用户自己模仿 | Agent **追问式引导**：像面试一样问出背景/动作/结果，从对话中挖出 STAR 素材存入知识库 |
| 转行/转方向 | 旧行业经历在新岗位 JD 里看不出关联 | 关键词匹配报告，用户自己改 | Agent 建立「旧经历→可迁移能力→新岗位任务」映射表，逐条改写并标注改写依据 |
| 多方向并行投递者（本项目 P1/P3 画像） | 十几版简历失控，记不清「腾讯那版突出了什么」 | 求职看板/Excel 追踪 | 版本树已有，Agent 补上「这版为什么这么改」的决策记录 |
| 非名校 | 怕被院校标签直接筛掉 | 把教育背景放最后，用户手动调 | Agent 按 JD 计算关键词覆盖度，自动建议栏目排序（已有 section_order 基础） |
| 长投无回应者 | 不知道是定位问题还是简历问题 | 只有润色建议 | Agent 抽取最近投递记录做**归因诊断**（定位 vs 关键词 vs 表达），给出结构化结论 |

### 2.4 用户画像（v2.0 修订）

保留 PRD.md 的 P1（算法工程师林）、P2（安全研究员陈）、P3（后端张），新增：

**P4 — 2026 届应届生「周」**
- 22 岁，计算机硕士应届，秋招同时投算法/开发/产品三方向
- 痛点：没有正式实习经历，课程项目和比赛不知道怎么写成简历语言；三方向要三份完全不同的简历，改不过来
- 期望：有个「懂行的师兄」反复追问自己，把零散经历挖出来、写成招聘语言，并且明确告诉自己哪版投哪个方向
- 关键行为：会用 ChatGPT 写简历但不知道 prompt 怎么写；对「AI 帮我编」既依赖又警惕

### 2.5 竞品对照结论

| 维度 | Rezi/Teal/Huntr | 国内工具 | Resume-Agent v2.0 |
|------|-----------------|----------|-------------------|
| 版本管理 | Teal 有限版本 | 基本没有 | ✅ Git 式版本树（已有） |
| Agent 编排 | 无（单次 LLM 调用） | WonderAI 对话修改（单一入口） | ✅ 多工具 Agent Loop + Reviewer 双审 |
| 过程透明 | 黑盒 | 黑盒 | ✅ SSE 流式展示 Agent 每步动作 |
| 诚实性约束 | 无（品类级翻车） | 无 | ✅ Reviewer + 知识库边界（已有基础） |
| 数据隐私 | 云端 SaaS | 云端 SaaS | ✅ 本地优先（已有） |
| 价格 | $9-30/月 | 免费+内购 | ✅ 开源自部署（已有） |

---

## 3. 现状诊断（代码级）

### 3.1 四个模块的具体问题

#### 模块 A：简历预览

| 问题 | 现状代码 | 影响 |
|------|----------|------|
| 双渲染引擎 WYSIWYG 风险 | 前端 HTML/CSS（ResumePreview.tsx）与后端 reportlab（pdf_builder.py）两套排版逻辑，靠 TemplateConfig 尽力对齐 | 预览与 PDF 可能有分页/换行差异，PRD 自己也列了「预览 vs PDF 逐像素一致率 ≥95%」为待验证项 |
| 无分页预览 | 前端整页滚动渲染，无 A4 分页指示 | 用户导出前不知道简历是 1 页还是 2 页——而「一页纸」是技术简历刚需 |
| 内联编辑字段不全 | EditableSummary/EditableText/EditableHighlights 已覆盖摘要/highlights，但个人联系方式、教育时间等仍走侧栏表单 | 编辑动线割裂：一半在预览里点、一半去表单里填 |

#### 模块 B：上传旧简历 → 提取信息

| 问题 | 现状代码 | 影响 |
|------|----------|------|
| 提取结果直接入树，无确认环节 | /parse 一次 LLM 提取后直接 TreeBuilder 写节点 | 提取错了（年份、公司名）用户只能事后在编辑器里逐项找出来改；错误数据还会进知识库被 RAG 检索放大 |
| 无字段级置信度 | 单次 LLM JSON 输出，全有或全无 | 用户不知道哪些字段可信、哪些要人工核对 |
| MinerU 阻塞式轮询 | 固定 2s 轮询、120s 超时 | 长简历/图片型 PDF 解析时前端一直转圈，超时即失败无重试 |
| 个人信息覆盖逻辑隐藏 | 解析后静默用知识库个人信息覆盖提取结果 | 用户不知道自己的电话/邮箱被替换了 |

#### 模块 C：实时编辑

| 问题 | 现状代码 | 影响 |
|------|----------|------|
| blur 才保存，无 debounce autosave | Editable 组件 onBlur → onChange | 焦点在输入框里时刷新页面/切节点 = 丢字 |
| AI 生成与手动编辑无冲突处理 | generate_full 直接 _save_node_content 覆盖整段 | 用户精调 30 分钟的内容可能被一次「重新生成」整段覆盖，无 diff 预览、无撤销 |
| 无 undo/redo | 前后端均无编辑历史 | 误删一段 highlights 只能重打 |
| 保存无版本快照 | 节点 content_json 单值，无历史 | 「上次生成的那版挺好的，找不回来了」 |

#### 模块 D：简历 Git 逻辑

| 问题 | 现状代码 | 影响 |
|------|----------|------|
| 合并范围仅 personal_info | upstream_changes/merge 端点只对比 personal_info 字段 | master 改了一段项目经历的 bullet，子分支永远不会知道——这是「简历森林」最核心的继承场景 |
| 内容段落无 diff 合并 | experience/projects/skills 只有只读 Diff 视图（tree/diff），无接受/拒绝 | 看得到差异，合并不了 |
| 无节点内 commit 历史 | resume_versions 每节点一份 content_json | 节点即终点，改坏了不能 revert；「Git 式管理」承诺只兑现了树形拓扑 |
| 硬删除级联 | 外键 ON DELETE CASCADE | 误删 company 节点，其定制内容瞬间蒸发，无回收站 |
| 上游检测靠刷新触发 | 前端轮询拉取 has_upstream_update | 不是事件驱动，master 改完子节点「3 秒内标记」实际依赖下一次刷新 |

### 3.2 Agent 架构现状

| 能力 | 现状 | 差距 |
|------|------|------|
| 工作流 | 固定三步函数链（检索→反思→撰写），每个环节单次 LLM 调用 | 无规划、无循环、LLM 不能自主决定「再检索一轮」或「这段素材不够换个查询」 |
| 工具协议 | 无 function calling / tool use，prompt 硬编码在函数里 | 现有能力（RAG 检索、JD 解析、Gap 分析、节点读写、模板渲染、PDF 导出、Tavily 搜索）无法被 LLM 按需调用 |
| 流式输出 | 后端零 SSE/WebSocket | 生成 30 秒全程转圈，无法展示过程 |
| 会话/记忆 | 无对话状态，每次请求独立 | 无法做追问式引导、无法记住用户偏好 |
| 人机协同 | AI 生成完直接覆盖节点 | 无 diff 预览门禁（human-in-the-loop） |

---

## 4. v2.0 产品需求

### 4.1 目标架构

```
用户意图（自然语言对话 / 传统按钮，两者并存）
        │
        ▼
┌─────────────────────────────────────────────┐
│           Orchestrator Agent（规划者）         │
│   deepseek function calling，SSE 流式输出     │
│   思考过程逐步推送到前端「Agent 行为面板」        │
└─────────────────────────────────────────────┘
        │ 工具调用（Agent 自主决定顺序与轮数）
        ▼
┌────────────────── 工具注册表 ──────────────────┐
│ retrieve_knowledge   知识库语义检索（已有 RAG）   │
│ parse_jd             JD 截图/文本结构化（已有）    │
│ analyze_gap          技能差距分析（已有）         │
│ read_node / write_node  版本树节点读写（已有）     │
│ render_preview       模板渲染预览（已有）         │
│ export_pdf           PDF 导出（已有）            │
│ web_search           Tavily 搜索（已有，tutor 在用）│
│ ask_user             反问用户，等待输入（新增）     │
└─────────────────────────────────────────────┘
        │ 产出草稿后
        ▼
┌─────────────────────────────────────────────┐
│         Reviewer Agent（审查者，独立上下文）     │
│  套话检测 / 事实边界核对（知识库外内容即标红）     │
│  JD 关键词覆盖检查 / 夸大表述降级建议            │
│  不合格 → 带意见打回 Orchestrator 重写（≤2 轮）  │
└─────────────────────────────────────────────┘
        │ 通过
        ▼
┌─────────────────────────────────────────────┐
│      Human Gate：diff 预览 → 逐字段接受/拒绝    │
│         （复用 v1.3 选择性合并的交互范式）        │
└─────────────────────────────────────────────┘
        │ 确认
        ▼
     写入版本树节点（带 commit 记录）
```

设计原则：
1. **过程透明**：Agent 每一步（思考、调用了什么工具、检索到什么、审查意见）通过 SSE 实时可见
2. **诚实性结构性保证**：Reviewer 独立上下文（对草稿无「忠诚度」），知识库边界外的内容默认标黄警告
3. **人始终在环上**：写操作默认走 diff 门禁，用户可对单次会话开启「信任模式」跳过
4. **按钮不消失**：传统点击流（传 JD→选节点→生成）保留，Agent 对话是并行入口，不是唯一入口

### 4.2 User Stories

#### P0 — Agent 地基（v2.0 必做，否则转型是空话）

**US-27：Agent Runtime 与工具注册表（A1）**
**As a** 开发者，**I want** 把现有后端能力封装为统一 schema 的 Agent 工具，**so that** LLM 能在循环中自主调用它们。

验收标准：
- [x] 定义 `Tool` 协议：name / description / parameters schema / execute
- [x] 首批封装 8 个工具：retrieve_knowledge、parse_jd、analyze_gap、read_node、write_node、render_preview、export_pdf、web_search
- [x] Agent Loop：deepseek function calling 多轮循环，最大轮数可配（默认 8）
- [x] 每轮的工具调用与结果记录为结构化 trace（SQLite 新表 agent_traces）
- [x] ask_user 工具：Agent 主动暂停等待用户输入，会话状态可恢复
- [x] 单元测试覆盖每个工具的 schema 校验与执行

**US-28：SSE 流式与 Agent 行为面板（A2）**
**As a** 求职者，**I want** 看到 Agent 正在做什么（思考、检索、审查），**so that** 我信任并理解产出结果。

验收标准：
- [x] 后端 `POST /api/agent/chat` 返回 `text/event-stream`
- [x] 事件类型：`thinking` / `tool_call` / `tool_result` / `review` / `draft` / `done` / `error`
- [x] 前端「Agent 行为面板」：时间线渲染每步动作，工具调用可展开看入参出参
- [x] 生成过程从「转圈 30s」变为「边看边等」
- [x] SSE 断线自动重连，会话不丢失

**US-29：对话式工作台（A3）**
**As a** 求职者（尤其 P4 应届生），**I want** 用自然语言和系统对话完成简历工作，**so that** 我不需要学习每个按钮在哪。

验收标准：
- [x] 右栏新增对话入口，支持：「帮我针对这个 JD 优化当前节点的项目经历」「我的经历太少怎么办」「把这段改得更量化」
- [x] Agent 能结合当前选中节点、已上传 JD、Gap 报告作为对话上下文
- [x] ask_user 触发时对话内出现输入卡片（如「这段项目你实际的贡献是什么？」）
- [x] 对话历史存 SQLite，刷新可恢复
- [x] 传统按钮流并存不删

#### P1 — 修复四个模块的结构性缺陷

**US-30：Reviewer Agent 双审机制（B1）**
**As a** 求职者，**I want** 生成内容经过独立审查才给我，**so that** 简历里没有 AI 套话和编造。

验收标准：
- [x] Reviewer 使用独立上下文（不复用 Orchestrator 的对话历史）
- [x] 检查项：知识库边界（素材外的内容标黄）、套话检测、JD 关键词覆盖、量化数字无来源标记
- [x] 不合格项带修改意见打回，最多 2 轮重写，仍不合格则如实展示问题
- [x] 审查意见随 diff 一起展示（「为什么这样改」）
- [x] 既有「反思」逻辑迁移并入 Reviewer，删除旧实现

**US-31：解析确认流（B2）**
**As a** 求职者，**I want** 上传旧简历后逐字段确认提取结果再入库，**so that** 错误数据不进版本树和知识库。

验收标准：
- [x] /parse 改为两阶段：提取（异步任务）→ 确认（用户审阅）→ 入库
- [x] 提取结果每个字段带置信度标记（高/中/低），低置信度字段高亮
- [x] 确认界面支持字段级编辑修正
- [x] 知识库个人信息覆盖逻辑改为可见提示（「检测到知识库已有电话，是否覆盖？」）
- [x] MinerU 解析改异步任务 + SSE 进度推送，超时自动降级本地解析器并提示
- [x] 确认后的数据才写入 resume_chunks（错误数据不再污染 RAG）

**US-32：编辑保护三件套（B3）**
**As a** 求职者，**I want** 编辑不丢字、AI 不覆盖我的精调、误删可撤销，**so that** 我敢放心编辑。

验收标准：
- [x] debounce autosave（800ms）替代纯 blur 保存，切节点/刷新前 flush
- [x] 节点 content_json 增加乐观锁 version 字段，保存冲突时提示而非静默覆盖
- [x] AI 生成/重生成结果默认以 **diff 预览卡片** 呈现（逐字段接受/拒绝），复用 v1.3 合并交互
- [x] 节点内编辑历史：每次写入记录轻量 commit（时间 + 摘要 + 完整 content_json 快照，保留最近 20 条）
- [x] undo/redo 快捷键（⌘Z/⌘⇧Z）基于 commit 历史
- [x] 节点删除改软删除 + 回收站（30 天），替代级联硬删除

#### P2 — Git 逻辑补完与体验收尾

**US-33：内容级上游合并（B4）**
**As a** 求职者，**I want** master 改了项目经历后子分支也能收到变更提示并选择性合并，**so that** 版本树的继承承诺完整兑现。

验收标准：
- [x] upstream_changes 检测范围扩展到 experience/projects/skills（段落级 + 条目级 diff）
- [x] 合并粒度：条目级（单条 bullet、单个项目）接受/拒绝
- [x] master 内容变更后子节点标记更新（前端 SSE 推送，替代轮询）
- [x] 合并交互复用 v1.3 Diff 视图范式
- [x] 检测算法有单元测试（同字段双向修改冲突场景）

**US-34：预览分页与一致性校验（C1）**
**As a** 求职者，**I want** 预览里看到 A4 分页线和总页数，**so that** 导出前就知道是不是一页纸。

验收标准：
- [x] ResumePreview 增加 A4 分页指示线与页码
- [x] 页数超出 1 页时提示（可配置目标页数）
- [x] 集成测试：预览分页断点与 PDF 分页断点一致率抽检（同内容同模板对比）

**US-35：Agent 记忆（C2）**
**As a** 求职者，**I want** Agent 记住我的偏好（如「不要动词开头堆砌」「我坚持两页纸」），**so that** 越用越顺手。

验收标准：
- [x] SQLite 新表 agent_memories（类型：偏好/纠错/风格样例）
- [x] Reviewer 审查时注入用户偏好记忆
- [x] 对话中「以后都……」类指令自动提炼为记忆，用户可在设置里查看/删除
- [x] 记忆注入有 token 上限控制（Top-K 相关记忆）

**US-36：应届生追问式冷启动（C3）**
**As a** 应届生，**I want** Agent 像师兄一样追问我的课程项目/比赛/社团，**so that** 零散经历变成简历语言。

验收标准：
- [x] 「素材挖掘」对话模式：逐条追问背景/动作/结果/量化，产出 STAR 结构素材
- [x] 挖掘出的素材直接进知识库（带来源标记「对话挖掘」）
- [x] 追问模板覆盖：课程设计、竞赛、科研、社团、实习五类
- [x] 中途可保存进度，下次继续
- [x] 素材去重（向量相似度查重）

### 4.3 明确不做（v2.0 Non-Goals）

- 自动投递/浏览器 Agent 操作招聘网站（道德与合规风险，且偏离简历管理主线）
- 多用户/协作、云端同步（延续 v1.x 排除项）
- 移动端适配
- LangGraph/LangChain 等重框架引入（延续自研函数链哲学，Agent Loop 自实现）
- 求职看板/投递时间线（竞品红海，版本树+Agent 已是差异化）
- 模板市场/自定义模板导入

---

## 5. 技术方案要点

### 5.1 Agent Loop（自实现，不引框架）

```python
# 形态示意（非最终实现）
while round < MAX_ROUNDS:
    response = await llm.chat(
        messages=history,
        tools=tool_registry.schemas(),   # OpenAI 协议 function calling
        stream=True,                     # SSE 逐 token 推送 thinking
    )
    for tool_call in response.tool_calls:
        trace = await tool_registry.execute(tool_call)  # 记入 agent_traces
        history.append(tool_result(trace))
    if response.final_draft:
        review = await reviewer_agent.review(response.final_draft)  # 独立上下文
        if review.passed: break
        history.append(review.feedback)  # 打回重写
```

- 依赖现有 [llm/client.py](backend/src/resume_agent/llm/client.py)（OpenAI 兼容协议已支持 deepseek，function calling 协议同源，无需新依赖）
- 会话状态：SQLite agent_sessions 表（messages JSON + 状态机 pending/awaiting_user/running/done）

### 5.2 SSE 通道

- FastAPI `StreamingResponse(media_type="text/event-stream")`，单连接单会话
- 前端用原生 EventSource 或 fetch-ReadableStream，断线指数退避重连
- 复用改造：generate_full（并行段落生成）与 MinerU 解析进度共用同一事件协议

### 5.3 工具注册表

现有代码迁移映射（能力已存在，只缺统一封装）：

| 工具 | 现有实现 | 封装动作 |
|------|----------|----------|
| retrieve_knowledge | api/knowledge.py 检索端点 | 抽 service 层，端点与工具共用 |
| parse_jd | api/jd.py + MinerU | 同上 |
| analyze_gap | api/gap_report.py | 同上 |
| read_node/write_node | api/tree.py | write_node 增加乐观锁与 commit 记录 |
| render_preview/export_pdf | api/export.py | 直接包装 |
| web_search | tutor 的 Tavily 调用 | 抽公共 service |
| ask_user | 无 | 新增：写会话状态 awaiting_user，SSE 推送问题，前端渲染输入卡片 |

### 5.4 数据库变更

```sql
-- 新表
CREATE TABLE agent_sessions (id, created_at, status, context_json, messages_json);
CREATE TABLE agent_traces (id, session_id, round, tool_name, input_json, output_json, created_at);
CREATE TABLE agent_memories (id, type, content, embedding, created_at, active);
CREATE TABLE node_commits (id, node_id, version, summary, content_json, created_at);
CREATE TABLE recycle_bin (node_id, content_json, deleted_at, expires_at);
-- 既有表
ALTER TABLE resume_versions ADD COLUMN content_version INTEGER DEFAULT 1;  -- 乐观锁
ALTER TABLE resume_versions ADD COLUMN deleted_at TEXT;                     -- 软删除
```

### 5.5 内容级合并算法

- 条目对齐：experience/projects 按（company+role）/(project name) 键匹配，未匹配项视为增/删
- 字段 diff：字符串用 difflib 行级，列表逐条对比（与现有 tree/diff 端点算法对齐复用）
- 冲突定义：同一字段在 master 与 child 都相对共同祖先变更 → 标记冲突，用户二选一（不做自动三方合并，控制复杂度）

---

## 6. 成功指标

| 指标 | 目标值 | 测量方式 |
|------|--------|----------|
| Agent 任务完成率 | ≥ 80% | 对话发起的生成任务，不因 Agent 死循环/工具失败而中断 |
| 生成内容套话率 | < 10%（v1 红线 15%） | 人工评审 20 份，Reviewer 打回机制上线前后对比 |
| 知识库边界违规率 | 0 | 生成内容与知识库素材比对，来源不可追溯的量化数字计数 |
| 首字节延迟（SSE） | ≤ 2s | 用户发送消息到看到 Agent 第一个思考事件 |
| 解析确认采纳率 | ≥ 70% | 确认界面上未修改直接采纳的会话占比（衡量提取质量） |
| 编辑丢失事故 | 0 | autosave + 乐观锁上线后，用户报告丢字数 |
| 对话式任务占比（自愿迁移度） | ≥ 30% | 30 天后新会话中对话入口发起的任务比例 |

---

## 7. 风险与缓解

| 风险 | 影响 | 概率 | 缓解 |
|------|------|------|------|
| deepseek function calling 稳定性/轮数失控 | 任务卡死或成本飙升 | 中 | 最大轮数硬上限 + 每轮超时 + trace 全记录便于回放调试 |
| Agent Loop 延迟高于固定链 | 用户等更久 | 中 | SSE 过程可见性补偿感知延迟；工具结果缓存 |
| Reviewer 与 Orchestrator 意见震荡 | 重写循环不收敛 | 中 | 打回上限 2 轮，仍不合格如实展示问题交人工 |
| 对话入口与传统按钮功能不一致 | 双入口维护成本 | 中 | 两者共用同一 service 层，按钮=预置参数的 Agent 调用 |
| SSE 代理环境兼容（nginx/浏览器） | 流式中断 | 低 | docker-compose 配置 X-Accel-Buffering，前端重连兜底 |
| 内容级合并冲突处理用户困惑 | 合并功能弃用 | 中 | 冲突字段二选一，不做自动合并；沿用 v1.3 已验证的交互范式 |
| commit 快照存储膨胀 | SQLite 变大 | 低 | 每节点保留最近 20 条快照，超限 FIFO 淘汰 |

---

## 8. 路线图

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **v2.0-alpha** | US-27 工具注册表 + Agent Loop + US-28 SSE/行为面板 | ✅ 已完成 |
| **v2.0-beta** | US-29 对话工作台 + US-30 Reviewer 双审 | ✅ 已完成 |
| **v2.0-rc** | US-31 解析确认流 + US-32 编辑保护三件套 | ✅ 已完成 |
| **v2.0** | US-33 内容级合并 + US-34 分页预览 + 发布 | ✅ 已完成 |
| **v2.1** | US-35 Agent 记忆 + US-36 应届生冷启动 | ✅ 已完成（提前交付） |

每阶段交付遵循 HJ Workflow：OpenSpec 规格 → 实现前评审 → TDD → QA → 人工验收。

---

## 附录：调研来源

- ai-job-search（GitHub 19.5K stars，drafter-reviewer 架构、诚实性约束、ATS 验证链路）
- AppliedIn（agentic pipeline：discover→score→tailor→review→approve→apply，human gate 默认开启）
- atsverification.com 2026 六工具×四 ATS 引擎横评（解析率数据、AI 编造数字结论）
- resumly.ai / huntr.co / syphonlabs.com 2026 市场格局与品类批评（碎片化、信任危机、周计费问题）
- 国内：超级简历/职徒/100分简历/ai简历姬产品分析（ATS 普及率、分人群选型、WonderAI 对话式修改）
- 本地代码审计：backend/src/resume_agent（api/services/parsers/llm/rag/export）、frontend/src/components、openspec/archive（18 个已归档规格）
