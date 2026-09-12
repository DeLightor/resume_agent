## 1. 规格和评审
- [x] 对照 PRD-v2.0 US-36 验收标准与当前代码，编写 proposal 与 design
- [x] 向 HJ 汇报设计方案并获得开工确认 (2026-09-11 获得授权)

## 2. 后端 TDD 与核心实现
- [x] 数据库更新：在 `schema.sql` 和 `init_db.py` 中添加 `material_mining_sessions` 表结构（保留既有 11 个节点与用户数据）
- [x] 挖掘业务服务实现：编写 `backend/src/resume_agent/services/material_mining.py`
  - 五大类别模板（课设、竞赛、科研、社团、实习）元数据定义
  - 会话 CRUD、状态机前进与问答上下文草稿保存（断点续挖）
  - LLM 交互式师兄追问生成与 STAR 结构化提炼引擎
  - Chroma 向量相似度语义查重服务（阈值判定）
  - 一键成果打包、保存物理 Markdown 文件并调用知识库切片向量化入库
- [x] API 路由实现：编写 `backend/src/resume_agent/api/mining.py` 端点并在 `api/router.py` 注册
- [x] 自动化测试套件编写：`backend/tests/test_material_mining.py`，覆盖模板加载、会话流转、断点续挖、STAR 提炼、向量查重与知识库提交入库

## 3. 前端界面实现
- [x] 前端类型与 API 封装：创建 `frontend/src/types/mining.ts` 与扩展 `frontend/src/lib/api.ts`
- [x] 素材挖掘抽屉组件：编写 `frontend/src/components/knowledge/MaterialMiningDrawer.tsx`
  - 类别选择与标题输入
  - S-T-A-R 状态机步骤条与问答交互
  - 师兄气泡与参考示例灵感快捷填充
  - 断点续挖草稿检测与恢复
  - STAR 成果预览微调、查重状态提示与确认入库
- [x] 知识库集成：在 `frontend/src/components/knowledge/KnowledgeView.tsx` 顶栏嵌入冷启动引导横幅与唤起触发

## 4. 自动化验证与质量检查
- [x] 执行后端单元测试与新接口测试：`pytest tests/test_material_mining.py` (8 passed)
- [x] 执行全量 Agent 相关与知识库回归测试：`pytest tests/test_*.py` (102 passed, total 110 passed)
- [x] 执行后端代码规范检查：`ruff check src tests` (All checks passed)
- [x] 执行前端类型检查与构建：`pnpm run typecheck` & `pnpm run build` (Passed)
- [x] 编写验证报告：`verification.md`

## 5. 人工验收与交付
- [x] 准备服务环境，提供给 HJ 详细的手工验证操作步骤
- [x] 等待 HJ 手工验收通过授权 (2026-09-12 获得 HJ 手工验收通过)
- [x] 经授权后归档 OpenSpec 并执行 Git commit / merge / push
