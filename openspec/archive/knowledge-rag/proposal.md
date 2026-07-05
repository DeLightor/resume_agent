# Proposal: knowledge-rag

## 概述

实现 US-3 知识库 RAG 功能：用户上传周报、论文、CTF 报告等素材，系统自动解析、分块、向量化并存储到本地 Chroma 向量库，支持语义检索。检索结果附带来源文档标注。

## 动机

当前 `api/knowledge.py` 为桩实现，`rag/embeddings.py` 的 `embed_texts` 未实现。用户需要建立个人知识库，为后续 AI 动态生成简历（US-6）和 Gap 报告（US-5）提供检索基础。

## 需求对齐

PRD US-3 验收标准：
- 支持 PDF、Word、Markdown、纯文本格式上传
- 文本切片（chunk size 512 tokens，overlap 50）
- 本地向量库（Chroma）存储，支持语义检索
- 左栏底部常驻知识库状态指示器（切片数、索引进度）
- 检索结果附带来源文档标注
- 索引 100 篇文档 ≤ 60s

## 变更范围

### 后端
1. **Embedding 实现**：`rag/embeddings.py` — 实现 `OpenAIEmbedding.embed_texts`，调用 OpenAI/DeepSeek API
2. **文本分块器**：新建 `rag/chunker.py` — 按字符数分块（512 chars ≈ 300 tokens 中文），overlap 50 chars
3. **知识库 API 重写**：`api/knowledge.py`
   - `POST /api/knowledge/upload` — 保存文件 → 创建 upload_record → 自动索引
   - `POST /api/knowledge/index/{upload_id}` — 解析文本 → 分块 → embedding → 存 Chroma + SQLite
   - `POST /api/knowledge/search` — Chroma 语义检索，返回 chunk_text + source_file + score
   - `GET /api/knowledge/documents` — 已上传文档列表
   - `DELETE /api/knowledge/documents/{upload_id}` — 删除文档及其切片
4. **测试**：`tests/test_knowledge_api.py` — 上传/索引/检索/列表/删除

### 前端
1. **KnowledgeStatus 联动**：从后端获取真实切片数和索引进度
2. **知识素材 UploadZone 接线**：第二个 UploadZone 调用 `/api/knowledge/upload`
3. **知识库文档列表**：点击"个人知识库"导航项时，中栏展示文档列表 + 检索框
4. **检索结果展示**：显示匹配文本片段 + 来源文件名 + 相似度分数

## 回滚方案

- 后端：revert 本次 commit，桩实现仍可用
- 前端：revert 后 KnowledgeStatus 回到硬编码值
- 数据库：无 schema 变更（knowledge_chunks 表已存在）
- Chroma：知识库集合可删除重建，不影响版本树数据
