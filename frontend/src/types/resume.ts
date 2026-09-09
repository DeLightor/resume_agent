// frontend/src/types/resume.ts
// 资产冷启动相关类型：结构化简历 / 上传 / 解析 / 列表

import type { ResumeNode } from './tree';

/** 解析状态 */
export type ParseStatus = 'pending' | 'parsing' | 'success' | 'needs_review' | 'failed';

/** 基础信息（对齐后端 extractor.BasicInfo 全字段） */
export interface BasicInfo {
  name: string | null;
  gender: string | null;
  birth_date: string | null;
  phone: string | null;
  email: string | null;
  location: string | null;
  website: string | null;
  github: string | null;
  linkedin: string | null;
}

/** 教育经历 */
export interface EducationItem {
  school: string | null;
  degree: string | null;
  major: string | null;
  period: string | null;
}

/** 工作经历 */
export interface ExperienceItem {
  company: string | null;
  role: string | null;
  period: string | null;
  highlights: string[];
}

/** 项目经历 */
export interface ProjectItem {
  name: string | null;
  role: string | null;
  description: string | null;
}

/**
 * LLM 提取的结构化简历数据。
 * 参考 design.md 第 2.3 节 ResumeExtractor.extract。
 */
export interface StructuredResume {
  basic: BasicInfo;
  education: EducationItem[];
  experience: ExperienceItem[];
  projects: ProjectItem[];
  skills: string[];
  /** 推断的主方向（安全/算法/后端/前端/数据/产品/其他） */
  primary_direction: string;
}

/** POST /api/resumes/upload 响应 data */
export interface UploadResponse {
  upload_id: string;
  file_name: string;
  file_type: string;
  parse_status: ParseStatus;
}

/** POST /api/resumes/parse 响应 data（US-31 两阶段：仅启动任务） */
export interface ParseStartResponse {
  task_id: string;
  status: 'extracting' | 'awaiting_confirm';
}

/** 解析任务状态 */
export type ParseTaskStatus = 'extracting' | 'awaiting_confirm' | 'confirmed' | 'failed';

/** 字段置信度级别（US-31：high=原文命中 / medium=条目部分命中 / low=未命中或缺失） */
export type ConfidenceLevel = 'high' | 'medium' | 'low';

/** 置信度映射：{section: {field_or_index: level}} */
export type ConfidenceMap = Record<string, Record<string, ConfidenceLevel>>;

/** SSE 解析进度事件 */
export type ParseTaskEvent =
  | { type: 'status'; task_id: string; status: ParseTaskStatus }
  | { type: 'file_parsed'; parser_used: 'mineru' | 'local'; degraded: boolean }
  | { type: 'extracting' }
  | { type: 'done'; task_id: string }
  | { type: 'error'; message: string };

/** GET /api/resumes/parse/tasks/{id} 响应 data */
export interface ParseTaskDetail {
  task_id: string;
  upload_id: string;
  status: ParseTaskStatus;
  parser_used: 'mineru' | 'local' | null;
  degraded: boolean;
  structured_resume: StructuredResume | null;
  confidence: ConfidenceMap | null;
  knowledge_personal_info: KnowledgePersonalInfo | null;
  error: string | null;
}

/** 知识库个人信息（确认界面覆盖选择用） */
export interface KnowledgePersonalInfo {
  contact: Partial<
    Record<
      'name' | 'gender' | 'birth_date' | 'phone' | 'email' | 'location' | 'website' | 'github' | 'linkedin',
      string
    >
  >;
  education: Array<{
    school?: string;
    degree?: string;
    major?: string;
    period?: string;
  }>;
  summary?: string;
}

/** POST /api/resumes/parse/tasks/{id}/confirm 请求体 */
export interface ConfirmParseRequest {
  structured_resume: StructuredResume;
  apply_knowledge_personal_info: boolean;
  custom_direction?: string;
}

/** POST /api/resumes/parse/tasks/{id}/confirm 响应 data */
export interface ParseResponse {
  upload_id: string;
  structured_resume: StructuredResume;
  tree_node: ResumeNode;
  /** 是否命中去重（同方向同公司已存在节点，仅更新内容） */
  deduplicated: boolean;
  /** 写入知识库的分块数 */
  knowledge_chunks: number;
  /** 版本已保存，但知识库索引未完成时的明确提示 */
  knowledge_warning?: string | null;
  direction?: string | null;
}

/** GET /api/resumes/list 列表项 */
export interface ResumeListItem {
  id: string;
  file_name: string;
  file_type: string;
  parse_status: ParseStatus;
  direction?: string | null;
  created_at: string;
}
