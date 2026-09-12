# US-36 应届生追问式冷启动 (Graduate Material Mining)

## Why
在 PRD-v2.0 规划中，目标用户群体涵盖应届生与跨方向求职者（用户画像 P4「周」）。
这类用户往往面临明显的“冷启动困境”：
1. **经历散落口语化**：没有成熟的商业实习经历，经历主要为课程设计大作业、竞赛、实验室科研、社团活动等，缺乏简历语言包装，写出来像流水账。
2. **知识库素材空白**：传统知识库依赖上传现成的 PDF/Word 简历或项目文档，应届生初始无现成文档可传，导致 RAG 检索无素材可用，AI 容易受限于无证据而无法生成充实内容。
3. **不知道该突出什么**：不清楚招聘方技术面试官看重什么指标（如并发、一致性、量化成果、排查过程），需要懂行的角色引导追问。

## What Changes
1. **持久化挖掘会话（Database Layer）**：
   - 在 SQLite 中建立 `material_mining_sessions` 表，记录挖掘会话的状态、分类、当前步骤、上下文问答草稿及提炼出的 STAR 结果，支持中途保存与断点续挖。
2. **五大类别追问模板与 STAR 引导引擎（Prompt & State Machine）**：
   - 覆盖五大经历分类：课程设计（`course_project`）、学科竞赛（`competition`）、科研课题（`research`）、社团活动（`club`）、兼职实习（`internship`）。
   - 采用 STAR 方法学状态机递进引导：
     - Step 1 (Situation)：项目背景、目标定位与分工。
     - Step 2 (Task)：核心职责与遇到的棘手挑战/瓶颈。
     - Step 3 (Action)：具体采取的技术方案、工具栈与攻坚步骤。
     - Step 4 (Result)：最终达成的指标、成果收益或客观评价。
3. **智能 STAR 结构化提炼（Synthesis）**：
   - 将零散口语化回答提炼为规范、高专业度的 ATS 友好简历 bullet points（包含动作动词、技术栈与量化指标）。
4. **知识库向量语义查重（Chroma Deduplication）**：
   - 入库前对生成的素材文本进行 Chroma 向量距离比对（相似度阈值），检测是否与现有知识库切片高度重复，防止垃圾与冗余数据膨胀。
5. **一键确认直接入库（RAG Ingestion）**：
   - 用户确认后，后端自动打包生成标准化 Markdown 素材资产（存入 `knowledge/` 目录并写入 `upload_records` 与 `knowledge_chunks`），标记来源为 `chat_mining`，即刻对接到后续简历生成的 RAG 证据链中。
6. **前端引导与交互抽屉（UI / UX）**：
   - 知识库面板顶部提供「💡 零经历冷启动 / 师兄帮你挖素材」横幅。
   - 向导式追问抽屉（`MaterialMiningDrawer`），展示 S-T-A-R 四步进度条、智能参考示例、STAR 预览卡片与查重提示。

## Impact
- **影响范围**：
  - 后端：`db/schema.sql`、`init_db.py`、新增 `services/material_mining.py`、新增 API 路由 `api/mining.py` 与 `api/router.py` 注册、联动 `knowledge.py` 与 `chroma_client.py`。
  - 前端：新增 `types/mining.ts`、新增 `components/knowledge/MaterialMiningDrawer.tsx`、修改 `components/knowledge/KnowledgeManagement.tsx` 增加引导横幅与抽屉唤起、API 客户端封装。
- **兼容性**：
  - 表结构幂等添加，不影响现有任何简历版本树或知识库数据。入库生成的资产符合现有 `upload_records` 规范。

## Rollback
- 如需回滚，切断前端入口与 `api/mining.py` 路由，新增的 `material_mining_sessions` 表与 `chat_mining` 素材不影响系统核心功能。
