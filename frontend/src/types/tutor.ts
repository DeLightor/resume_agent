// frontend/src/types/tutor.ts
// AI 导师学习建议相关类型（US-11）

/** 学习路径三步 */
export interface LearningPath {
  concept: string;
  practice: string;
  validation: string;
}

/** 学习资源 */
export interface TutorResource {
  type: 'document' | 'course' | 'project' | 'interview';
  title: string;
  url: string;
  description: string;
}

/** 单项学习建议 */
export interface TutorSuggestion {
  skill: string;
  category?: string;
  status: 'missing' | 'partial';
  learning_path: LearningPath;
  resources: TutorResource[];
}

/** POST /api/tutor/suggest 响应 data */
export interface TutorResult {
  suggestions: TutorSuggestion[];
}

/** 学习状态 */
export type LearnStatus = 'mastered' | 'learning' | 'pending';
