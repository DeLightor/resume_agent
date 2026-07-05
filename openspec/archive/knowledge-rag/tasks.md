# Tasks: knowledge-rag

## 后端
- [x] 实现 `OpenAIEmbedding.embed_texts`（保留备用，当前使用 Chroma 内置模型）
- [x] 新建 `rag/chunker.py`：文本分块（512 chars, overlap 50）
- [x] 新增 MD/TXT 解析（直接读取）
- [x] 重写 `POST /api/knowledge/upload`：保存文件 + 自动索引
- [x] 重写 `POST /api/knowledge/index/{upload_id}`：解析→分块→Chroma 本地 embedding→存 Chroma+SQLite
- [x] 重写 `POST /api/knowledge/search`：Chroma 语义检索（query_texts）
- [x] 新增 `GET /api/knowledge/documents`：文档列表
- [x] 新增 `DELETE /api/knowledge/documents/{upload_id}`：删除文档及切片
- [x] 新增 `GET /api/knowledge/stats`：切片数、文档数、状态
- [x] 测试：上传→索引→检索 全链路（28 测试全通过）
- [x] 测试：不支持的格式、空文件、重复上传

## 前端
- [x] KnowledgeStatus：从 `/api/knowledge/stats` 获取真实数据
- [x] 第二个 UploadZone 接线：调用 `uploadKnowledge` API
- [x] 新增 `KnowledgeView` 组件：文档列表 + 检索框 + 检索结果
- [x] CenterPanel：导航切换到"个人知识库"时显示 KnowledgeView
- [x] api.ts：新增 uploadKnowledge / searchKnowledge / getKnowledgeDocuments / getKnowledgeStats / deleteKnowledgeDocument
- [x] types/knowledge.ts：类型定义

## 验证
- [x] 后端 pytest（28 通过） + ruff
- [x] 前端 typecheck + build
