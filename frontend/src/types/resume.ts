// frontend/src/types/resume.ts
// 资产冷启动相关类型：结构化简历 / 上传 / 解析 / 列表

import type { ResumeNode } from './tree';

/** 解析状态 */
export type ParseStatus = 'pending' | 'parsing' | 'success' | 'needs_review' | 'failed';

/** 基础信息 */
export interface BasicInfo {
  name: string | null;
  phone: string | null;
  email: string | null;
  location: string | null;
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

/** POST /api/resumes/parse 响应 data */
export interface ParseResponse {
  structured_resume: StructuredResume;
  tree_node: ResumeNode;
  /** 是否命中去重（同方向同公司已存在节点，仅更新内容） */
  deduplicated: boolean;
}

/** GET /api/resumes/list 列表项 */
export interface ResumeListItem {
  id: string;
  file_name: string;
  file_type: string;
  parse_status: ParseStatus;
  created_at: string;
}
