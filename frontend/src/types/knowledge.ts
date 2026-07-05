// frontend/src/types/knowledge.ts
// 知识库 RAG 相关类型：文档 / 统计 / 检索结果 / 上传响应

/** 中栏视图切换（US-3 引入知识库视图） */
export type ActiveView = 'version-tree' | 'knowledge';

/** 知识库文档解析状态 */
export type KnowledgeParseStatus =
  | 'pending'
  | 'parsing'
  | 'success'
  | 'failed'
  | 'needs_review';

/** 知识库文档（GET /api/knowledge/documents 列表项） */
export interface KnowledgeDocument {
  id: string;
  file_name: string;
  file_type: string;
  parse_status: KnowledgeParseStatus;
  created_at: string;
}

/** 知识库统计（GET /api/knowledge/stats） */
export interface KnowledgeStats {
  chunk_count: number;
  document_count: number;
  indexing_status: string;
}

/** 检索单条结果（POST /api/knowledge/search results 项） */
export interface SearchResult {
  chunk_id: string;
  source_file: string;
  chunk_text: string;
  score: number;
}

/** POST /api/knowledge/search 响应 data */
export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

/** POST /api/knowledge/upload 响应 data */
export interface KnowledgeUploadResponse {
  id: string;
  file_name: string;
  file_type: string;
  parse_status: string;
  chunk_count: number;
}
