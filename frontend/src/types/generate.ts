// frontend/src/types/generate.ts
// AI 生成结果相关类型（US-6）

/** 反思审核结果 */
export interface Reflection {
  issues_found: number;
  issues: { type: string; description: string; source: string }[];
  notes: string;
}

/** 生成的工作经历条目 */
export interface GeneratedExperience {
  company: string;
  role: string;
  period: string;
  highlights: string[];
}

/** 生成的项目条目 */
export interface GeneratedProject {
  name: string;
  role: string;
  period: string;
  description: string;
  tech_stack: string[];
}

/** 生成的技能 */
export interface GeneratedSkill {
  name: string;
  context: string;
}

export interface GeneratedSkills {
  tech_stack: GeneratedSkill[];
  hard_skills: GeneratedSkill[];
  soft_skills: GeneratedSkill[];
}

/** POST /api/generate 响应 data */
export interface GenerateResult {
  section: string;
  content: Record<string, unknown>;
  reflection: Reflection;
  sources_used: number;
}
