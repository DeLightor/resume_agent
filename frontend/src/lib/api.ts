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
import type { JDAnalysisResult } from '@/types/jd';
import type { GapReport } from '@/types/gap';
import type { GenerateResult } from '@/types/generate';
import type { SuggestResult } from '@/types/suggest';
import type { TemplateInfo } from '@/types/template';
import type { DiffResult } from '@/types/diff';
import type { TutorResult } from '@/types/tutor';
import type { PersonalInfo } from '@/types/personal';
import type { SectionItem } from '@/types/section';

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

/**
 * 删除节点及其所有子孙节点（US-12 补充）。
 * DELETE /api/tree/node/{node_id}
 */
export async function deleteNode(
  nodeId: string,
): Promise<{ deleted_count: number }> {
  return api.del<{ deleted_count: number }>(
    `/tree/node/${encodeURIComponent(nodeId)}`,
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

// ===== JD 截图分析相关 API（US-4）=====

/**
 * 上传职位文件（截图/PDF/TXT，支持多文件）并触发 LLM 结构化分析。
 * multipart/form-data，后端 OCR + LLM 提取岗位/公司/技术栈/技能等（含去重）。
 */
export async function analyzeJD(files: File[]): Promise<JDAnalysisResult> {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  return api.upload<JDAnalysisResult>('/jd/analyze', formData);
}

// ===== Gap 报告 API（US-5）=====

/**
 * 生成技能 Gap 报告。
 * POST /api/gap-report，传入 JD 结构化数据，返回三色状态报告。
 */
export async function generateGapReport(
  structuredJD: Record<string, unknown>,
): Promise<GapReport> {
  return api.post<GapReport>('/gap-report', { structured_jd: structuredJD });
}

// ===== AI 生成 API（US-6）=====

/**
 * AI 生成简历段落。
 * POST /api/generate，3 步工作流：检索 → 反思 → 撰写。
 */
export async function generateResume(
  structuredJD: Record<string, unknown>,
  section: string,
  gapReport?: Record<string, unknown> | null,
): Promise<GenerateResult> {
  return api.post<GenerateResult>('/generate', {
    structured_jd: structuredJD,
    section,
    gap_report: gapReport ?? null,
  });
}

// ===== PDF 导出 API（US-7）=====

/**
 * 导出简历为 PDF。
 * POST /api/export/pdf，返回 PDF 文件（Blob）。
 *
 * 注意：此 API 返回的是二进制文件（application/pdf），不是标准 JSON envelope，
 * 因此不能用 apiRequest 封装，需要直接用 fetch 并以 blob 方式接收。
 */
export async function exportResumePDF(
  resumeData: Record<string, unknown>,
  jobTitle?: string,
  company?: string,
  templateId?: string,
): Promise<Blob> {
  const response = await fetch(`${BASE_URL}/export/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      resume_data: resumeData,
      job_title: jobTitle ?? '',
      company: company ?? '',
      template_id: templateId ?? 'modern',
    }),
  });

  if (!response.ok) {
    throw new Error(`导出失败: HTTP ${response.status}`);
  }

  // 检查是否是错误 JSON 响应（后端错误时返回 JSON）
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) {
    const errorData = await response.json();
    throw new Error(errorData?.error?.message ?? '导出失败');
  }

  return response.blob();
}

// ===== 模板系统 API（US-8）=====

/**
 * 获取模板列表。
 * GET /api/templates，返回内置模板（modern / classic / tech）。
 * 每项包含 id / name / description / theme_color。
 */
export async function getTemplates(): Promise<TemplateInfo[]> {
  return api.get<TemplateInfo[]>('/templates');
}

// ===== AI 智能补全 API（US-9）=====

/**
 * 获取 AI 智能补全建议。
 * POST /api/suggest，传入 JD 结构化数据 + 当前段落内容，返回可采纳的补充建议。
 */
export async function generateSuggestions(
  structuredJD: Record<string, unknown>,
  section: string,
  content: Record<string, unknown>,
  gapReport?: Record<string, unknown> | null,
): Promise<SuggestResult> {
  return api.post<SuggestResult>('/suggest', {
    structured_jd: structuredJD,
    section,
    content,
    gap_report: gapReport ?? null,
  });
}

// ===== 版本 Diff API（US-10）=====

/** 对比两个节点的 content_json */
export async function getNodeDiff(
  nodeAId: string,
  nodeBId: string,
): Promise<DiffResult> {
  return api.post<DiffResult>('/diff', {
    node_a_id: nodeAId,
    node_b_id: nodeBId,
  });
}

/** 更新节点的 content_json（保存简历内容到节点） */
export async function updateNodeContent(
  nodeId: string,
  content: Record<string, unknown>,
): Promise<void> {
  await api.put(`/tree/node/${nodeId}`, { content_json: content });
}

// ===== AI 导师 API（US-11）=====

/**
 * 获取 AI 导师学习建议。
 * POST /api/tutor/suggest，传入 Gap 报告技能项，返回学习路径和资源推荐。
 */
export async function getTutorSuggestions(
  items: { skill: string; category: string; status: string }[],
): Promise<TutorResult> {
  return api.post<TutorResult>('/tutor/suggest', { items });
}

// ===== 个人信息 API（US-12）=====

/** 获取节点的个人信息 */
export async function getPersonalInfo(nodeId: string): Promise<PersonalInfo> {
  const result = await api.get<{ personal_info: PersonalInfo }>(
    `/tree/node/${nodeId}/personal-info`,
  );
  return result.personal_info;
}

/** 更新节点的个人信息 */
export async function updatePersonalInfo(
  nodeId: string,
  info: PersonalInfo,
): Promise<void> {
  await api.put(`/tree/node/${nodeId}/personal-info`, info);
}

/** 从知识库提取个人信息 */
export async function extractPersonalInfo(): Promise<PersonalInfo> {
  const result = await api.post<{ personal_info: PersonalInfo }>(
    '/personal-info/extract',
    {},
  );
  return result.personal_info;
}

/** US-14: 一键生成整份简历 */
export async function generateFull(
  nodeId: string,
  structuredJd?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return api.post<Record<string, unknown>>('/generate/full', {
    node_id: nodeId,
    structured_jd: structuredJd,
  });
}

/** US-14: 单段重新生成 */
export async function regenerateSection(
  nodeId: string,
  section: string,
  structuredJd?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return api.post<Record<string, unknown>>('/generate/section', {
    node_id: nodeId,
    section,
    structured_jd: structuredJd,
  });
}

/** 获取节点的段落顺序 */
export async function getSectionOrder(nodeId: string): Promise<SectionItem[]> {
  const result = await api.get<{ sections: SectionItem[] }>(
    `/tree/node/${nodeId}/section-order`,
  );
  return result.sections;
}

/** 更新节点的段落顺序 */
export async function updateSectionOrder(
  nodeId: string,
  sections: SectionItem[],
): Promise<void> {
  await api.put(`/tree/node/${nodeId}/section-order`, { sections });
}

/** US-15: 完整性检测 */
export async function checkCompleteness(
  nodeId: string,
): Promise<{ score: number; checks: Array<Record<string, unknown>> }> {
  const result = await api.post<{ score: number; checks: Array<Record<string, unknown>> }>(
    '/completeness/check',
    { node_id: nodeId },
  );
  return result;
}

/** US-15: 编辑段落 */
export async function updateSection(
  nodeId: string,
  section: string,
  data: unknown,
): Promise<void> {
  await api.put(`/tree/node/${nodeId}/section`, { section, data });
}

// === US-17: 上游变更检测 ===

export interface UpstreamChanges {
  has_upstream_update: boolean;
  changes: Record<string, { old: unknown; new: unknown }>;
  count: number;
}

export async function getUpstreamChanges(nodeId: string): Promise<UpstreamChanges> {
  const res = await api.get<UpstreamChanges>(`/tree/node/${nodeId}/upstream-changes`);
  return res;
}

export async function mergeField(nodeId: string, field: string): Promise<{ merged: boolean; remaining_changes: number }> {
  const res = await api.post<{ merged: boolean; remaining_changes: number }>(`/tree/node/${nodeId}/merge`, { field });
  return res;
}

export async function mergeAll(nodeId: string): Promise<{ merged_count: number; all_merged: boolean }> {
  const res = await api.post<{ merged_count: number; all_merged: boolean }>(`/tree/node/${nodeId}/merge/all`);
  return res;
}
