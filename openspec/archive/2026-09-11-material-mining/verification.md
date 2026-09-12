# US-36 验证报告：应届生追问式冷启动 (素材挖掘)

## 1. 验证目标
验证 US-36 应届生追问式冷启动（Graduate Material Mining）核心能力：
1. 数据库 `material_mining_sessions` 持久化表与幂等初始化。
2. 五大分类模板（课设、竞赛、科研、社团、实习）元数据加载与引导。
3. 师兄式 STAR 四步状态机递进问答、断点续挖与进度保存。
4. STAR 结构化成果提炼与高质量简历 Bullet Points 生成。
5. Chroma 语义向量查重（相似度阈值判定）。
6. 一键自动化打包入库：生成 Markdown 物理文件、写入 upload_records 与 knowledge_chunks 并完成 Chroma 索引。
7. 前端冷启动横幅、引导抽屉、草稿恢复、预览微调与提交反馈。

---

## 2. 自动化测试与检查结果

### 2.1 后端单元测试与 API 测试 (`pytest tests/test_material_mining.py`)
- **8 passed in 13.54s**
  1. `test_get_mining_templates`: 验证五大分类模板元数据（课设、竞赛、科研、社团、实习）正确加载
  2. `test_create_and_get_session`: 验证会话创建、字段持久化与获取详情
  3. `test_create_session_invalid_category`: 验证非法类别校验
  4. `test_submit_step_answer_progression`: 验证步骤流转 (1 -> 2 -> 3 -> 4 -> 5) 与草稿上下文保存
  5. `test_synthesize_star_result`: 验证 STAR 结构化提炼与技术栈/Bullet Points 生成
  6. `test_check_duplicate_in_knowledge`: 验证 Chroma 向量检索与余弦相似度查重阈值判定 (>= 0.85)
  7. `test_commit_mining_to_knowledge`: 验证物理 Markdown 生成、upload_records 登记、knowledge_chunks 写入与 Chroma 索引闭环
  8. `test_mining_api_endpoints`: 验证 FastAPI 完整 REST API 端点流转与 HTTP 响应

### 2.2 全量 Agent 回归测试 (`pytest tests/test_agent_*.py`)
- **102 passed in 2.35s** (零回归，历史全量功能保持完好)
- 全局测试总计：**110 passed**

### 2.3 后端代码规范检查 (`ruff check src tests`)
- **All checks passed!** (0 errors, 0 warnings)

### 2.4 前端 TypeScript 检查与生产构建
- `pnpm run typecheck`: **Pass** (0 errors)
- `pnpm run build`: **Pass** (Vite 生产构建耗时 587ms，产物完整)

### 2.5 用户既有数据完整性
- 查询 `sqlite3 ~/.resume-agent/data.db "SELECT count(*) FROM resume_versions;"`：**11 份历史版本完整保留**

---

## 3. 运行服务状态
- **后端服务**：`http://127.0.0.1:8000` (FastAPI + Uvicorn 正常运行，热重载完成，`/api/mining/*` 接口已激活)
- **前端服务**：`http://127.0.0.1:5173` (Vite 开发服务器正常运行，HMR 正常分发)
- **进程资源**：无冗余浏览器进程或后台死循环占用 CPU/内存

---

## 4. 人工冒烟验收与问题闭环
- **验收人**：HJ
- **验收日期**：2026-09-12
- **验收发现**：
  - 经历深度挖掘全流程（模板选择、S-T-A-R 追问状态机、师兄点评、STAR 提炼、向量查重与沉淀入库）功能完整，符合预期。
  - 发现素材挖掘产物在知识库视图中同时显示在「已确认的简历」列表中。
- **闭环修复**：
  - 在 `backend/src/resume_agent/api/resumes.py` 的 `list_resumes` 接口增加 `WHERE file_path LIKE 'resumes/%'` 严格隔离。
  - 在 `frontend/src/components/knowledge/KnowledgeView.tsx` 中增加多重过滤（排除非简历文件及 `chat_mining` 属性）。
  - 素材挖掘成果纯净归属为「知识素材文档」，直接进入知识库 RAG 资产供检索与简历生成使用。
- **最终结论**：HJ 确认无误，验收通过，授权归档合并。


