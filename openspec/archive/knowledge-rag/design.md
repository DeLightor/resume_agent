# Design: knowledge-rag

## 1. 架构概览

```
用户上传素材 → 保存文件 → upload_records 记录
                           ↓
                      解析文本 (PDF/DOCX/MD/TXT)
                           ↓
                      文本分块 (512 chars, overlap 50)
                           ↓
                      Embedding (OpenAI text-embedding-3-small)
                           ↓
              ┌────────────┴────────────┐
              ↓                          ↓
        Chroma 向量库               SQLite knowledge_chunks
        (embedding_id)              (chunk_text, source_file)
              ↓
      语义检索 (cosine similarity)
```

## 2. 后端设计

### 2.1 Embedding 实现 (`rag/embeddings.py`)

`OpenAIEmbedding.embed_texts` 使用 `openai.OpenAI` 同步客户端（非 async）：
- 模型：`settings.embedding_model`（默认 `text-embedding-3-small`，1536 维）
- API：兼容 OpenAI 协议，支持 DeepSeek base_url
- 批处理：每批最多 100 条文本
- 返回 `list[list[float]]`

```python
class OpenAIEmbedding(EmbeddingProvider):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url or None)
        result = client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in result.data]
```

### 2.2 文本分块器 (`rag/chunker.py`)

按字符数分块（中文字符占 1 个 char ≈ 0.5 token）：
- `CHUNK_SIZE = 512`（字符）
- `CHUNK_OVERLAP = 50`（字符）
- 返回 `list[str]`，每个 chunk 为纯文本

```python
def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks
```

### 2.3 知识库 API (`api/knowledge.py`)

#### POST /api/knowledge/upload
- 接收 multipart/form-data 文件
- 保存到 `~/.resume-agent/files/knowledge/{uuid}.{ext}`
- 创建 `upload_records` 记录
- 自动触发索引流程
- 返回 upload record + chunk_count

#### POST /api/knowledge/index/{upload_id}
- 从 upload_record 获取 file_path
- 按文件类型解析文本（复用已有 PDF/DOCX 解析器，新增 MD/TXT）
- 调用 `chunk_text` 分块
- 调用 `OpenAIEmbedding.embed_texts` 生成向量
- 存入 Chroma `knowledge_chunks` 集合（embedding_id = uuid）
- 存入 SQLite `knowledge_chunks` 表（chunk_text, source_file, embedding_id）
- 更新 upload_record.parse_status = 'success'

#### POST /api/knowledge/search
- 请求体：`{query: str, top_k: int = 5}`
- 对 query 做 embedding
- Chroma `knowledge_chunks` 集合 `query` 方法
- 返回 `[{chunk_id, source_file, chunk_text, score}]`

#### GET /api/knowledge/documents
- 从 `upload_records` 表查询所有知识库文档（file_type in md/txt/pdf/docx）
- 返回 `[{id, file_name, file_type, parse_status, created_at}]`

#### DELETE /api/knowledge/documents/{upload_id}
- 删除 SQLite `knowledge_chunks` 表中该 source_file 的所有切片
- 删除 Chroma 中对应 embedding_id
- 删除 `upload_records` 记录
- 删除物理文件

#### GET /api/knowledge/stats
- 返回 `{chunk_count, document_count, indexing_status}`
- 供前端 KnowledgeStatus 组件使用

### 2.4 文件解析

复用已有：
- PDF: `parsers/pdf_parser.py` → `extract_text_from_pdf`
- DOCX: `parsers/docx_parser.py` → `extract_text_from_docx`

新增：
- MD/TXT: 直接读取文件内容

## 3. 前端设计

### 3.1 KnowledgeStatus 联动

```tsx
// 启动时和上传后调用 GET /api/knowledge/stats
const { chunkCount, document_count } = await getKnowledgeStats();
```

### 3.2 知识素材 UploadZone

第二个 UploadZone 的 `onFileUploaded` 调用 `uploadKnowledge(file)` API，成功后刷新 stats。

### 3.3 知识库视图

当左侧导航选中"个人知识库 (RAG)"时，CenterPanel 切换为知识库管理视图：
- 顶部：检索框（输入关键词 → 语义检索）
- 中部：文档列表（文件名、类型、状态、创建时间、删除按钮）
- 检索结果区：匹配文本片段 + 来源文件 + 相似度分数

### 3.4 API 封装 (`lib/api.ts`)

```typescript
uploadKnowledge(file: File): Promise<KnowledgeUploadResponse>
searchKnowledge(query: string, topK?: number): Promise<SearchResult[]>
getKnowledgeDocuments(): Promise<KnowledgeDocument[]>
getKnowledgeStats(): Promise<KnowledgeStats>
deleteKnowledgeDocument(uploadId: string): Promise<void>
```

## 4. 测试策略

- 后端：上传 → 索引 → 检索 全链路集成测试（mock embedding）
- 前端：typecheck + build
- 边界：空文件、超大文件、不支持的格式、重复上传
