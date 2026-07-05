// frontend/src/lib/api.ts
// API 调用封装（fetch wrapper），统一处理 ok/data/error 格式

import type {
  ApiResponse,
  CreateNodeRequest,
  ResumeNode,
  TreeData,
  UpdateNodeRequest,
} from '@/types/tree';
import type {
  ParseResponse,
  ResumeListItem,
  UploadResponse,
} from '@/types/resume';
import type {
  KnowledgeDocument,
  KnowledgeStats,
  KnowledgeUploadResponse,
  SearchResponse,
} from '@/types/knowledge';

const BASE_URL = '/api';

/**
 * 统一 fetch 封装，自动解析 ApiResponse envelope。
 * 返回 data 部分（ok=true 时），或抛出 Error（ok=false 时）。
 *
 * 当 body 为 FormData 时，不设置默认 Content-Type，
 * 由浏览器自动注入 multipart/form-data + boundary。
 */
export async function apiRequest<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const isFormData = options?.body instanceof FormData;

  const res = await fetch(url, {
    ...options,
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...options?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }

  const json: ApiResponse<T> = await res.json();

  if (!json.ok) {
    throw new Error(json.error?.message ?? 'Unknown error');
  }

  return json.data as T;
}

/** 便捷方法 */
export const api = {
  get: <T>(endpoint: string) =>
    apiRequest<T>(endpoint, { method: 'GET' }),

  post: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  upload: <T>(endpoint: string, formData: FormData) =>
    apiRequest<T>(endpoint, {
      method: 'POST',
      body: formData,
      // 不设置 Content-Type，让浏览器自动设置 multipart boundary
    }),

  put: <T>(endpoint: string, body?: unknown) =>
    apiRequest<T>(endpoint, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    }),

  del: <T>(endpoint: string) =>
    apiRequest<T>(endpoint, { method: 'DELETE' }),
};

// ===== 资产冷启动相关 API（参考 design.md 第 3 节）=====

/**
 * 上传简历文件（PDF/DOCX）。
 * multipart/form-data，后端保存文件并创建 upload_records 记录。
 */
export async function uploadResume(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return api.upload<UploadResponse>('/resumes/upload', formData);
}

/**
 * 触发简历解析。
 * 后端：提取文本 → LLM 结构化 → 生成/更新版本树节点。
 */
export async function parseResume(uploadId: string): Promise<ParseResponse> {
  return api.post<ParseResponse>('/resumes/parse', { upload_id: uploadId });
}

/**
 * 获取版本树（从 resume_versions 表构建）。
 */
export async function getTree(): Promise<TreeData> {
  return api.get<TreeData>('/tree');
}

/**
 * 获取已上传简历列表。
 */
export async function getResumeList(): Promise<ResumeListItem[]> {
  return api.get<ResumeListItem[]>('/resumes/list');
}

// ===== 版本树节点管理 API（US-2）=====

/**
 * 获取单个节点详情（含 content_json）。
 * GET /api/tree/{node_id}
 */
export async function getNode(nodeId: string): Promise<ResumeNode> {
  return api.get<ResumeNode>(`/tree/${encodeURIComponent(nodeId)}`);
}

/**
 * 新建节点（branch / company），写入 resume_versions 表。
 * POST /api/tree/node
 */
export async function createNode(req: CreateNodeRequest): Promise<ResumeNode> {
  return api.post<ResumeNode>('/tree/node', req);
}

/**
 * 更新节点 title / content_json。
 * PUT /api/tree/node/{node_id}
 */
export async function updateNode(
  nodeId: string,
  updates: UpdateNodeRequest,
): Promise<ResumeNode> {
  return api.put<ResumeNode>(
    `/tree/node/${encodeURIComponent(nodeId)}`,
    updates,
  );
}

// ===== 知识库 RAG 相关 API（US-3）=====

/**
 * 上传知识素材文件（PDF/DOCX/MD/TXT 等）。
 * multipart/form-data，后端保存文件并写入 knowledge_documents 表。
 */
export async function uploadKnowledge(
  file: File,
): Promise<KnowledgeUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return api.upload<KnowledgeUploadResponse>(
    '/knowledge/upload',
    formData,
  );
}

/**
 * 语义检索知识库。
 * POST /api/knowledge/search，返回 query + 命中片段列表。
 */
export async function searchKnowledge(
  query: string,
  topK?: number,
): Promise<SearchResponse> {
  return api.post<SearchResponse>('/knowledge/search', {
    query,
    top_k: topK,
  });
}

/**
 * 获取知识库文档列表。
 * GET /api/knowledge/documents
 */
export async function getKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  return api.get<KnowledgeDocument[]>('/knowledge/documents');
}

/**
 * 获取知识库统计信息（切片数 / 文档数 / 索引状态）。
 * GET /api/knowledge/stats
 */
export async function getKnowledgeStats(): Promise<KnowledgeStats> {
  return api.get<KnowledgeStats>('/knowledge/stats');
}

/**
 * 删除知识库文档（连同其切片向量）。
 * DELETE /api/knowledge/documents/{uploadId}
 */
export async function deleteKnowledgeDocument(
  uploadId: string,
): Promise<void> {
  await api.del<null>(`/knowledge/documents/${encodeURIComponent(uploadId)}`);
}
