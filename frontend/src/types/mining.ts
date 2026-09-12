// frontend/src/types/mining.ts
// 应届生追问式冷启动（素材挖掘）相关类型定义 (US-36)

export type MiningCategory =
  | 'course_project'
  | 'competition'
  | 'research'
  | 'club'
  | 'internship';

export interface MiningStepInfo {
  step: number;
  title: string;
  question: string;
  example: string;
}

export interface MiningTemplate {
  category: MiningCategory;
  title: string;
  icon: string;
  description: string;
  steps: MiningStepInfo[];
}

export interface StarResult {
  summary: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  tech_stack: string[];
  bullet_points: string[];
}

export interface DuplicateMatch {
  chunk_id: string;
  source_file: string;
  chunk_text: string;
  score: number;
}

export interface DuplicateCheckResult {
  is_duplicate: boolean;
  max_score: number;
  threshold: number;
  similar_chunks: DuplicateMatch[];
}

export interface MiningStepAnswer {
  step: number;
  step_title: string;
  question: string;
  user_answer: string;
  ai_feedback?: string;
  answered_at?: string;
}

export interface MiningContextJson {
  category: string;
  title: string;
  answers: MiningStepAnswer[];
}

export type MiningSessionStatus = 'in_progress' | 'completed' | 'abandoned';

export interface MaterialMiningSession {
  id: string;
  category: MiningCategory;
  title: string;
  status: MiningSessionStatus;
  current_step: number; // 1: S, 2: T, 3: A, 4: R, 5: 提炼完成
  context_json: MiningContextJson;
  star_result_json?: StarResult | null;
  created_at: string;
  updated_at: string;
}

export interface CreateMiningSessionParams {
  category: MiningCategory;
  title: string;
}

export interface SubmitMiningAnswerParams {
  step: number;
  answer: string;
}

export interface SubmitMiningAnswerResponse {
  session_id: string;
  step: number;
  ai_feedback: string;
  next_step: number;
  is_last_step: boolean;
}

export interface SynthesizeMiningResultResponse {
  star_result: StarResult;
  duplicate_check: DuplicateCheckResult | null;
}

export interface CommitMiningResultResponse {
  upload_id: string;
  file_name: string;
  chunk_count: number;
  message: string;
}
