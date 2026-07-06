// frontend/src/types/suggest.ts
// AI 智能补全建议相关类型（US-9）

/** 单条补全建议 */
export interface Suggestion {
  field: string;           // "experience[0].highlights"
  type: string;            // "add_highlight" / "add_detail" / "add_tech_stack" / "add_skill_context"
  suggested_text: string;  // 建议补充的文本
  reason: string;          // 为什么要补充
  source: string;          // "知识库检索: work_notes.md (相关度 0.78)"
}

/** POST /api/suggest 响应 data */
export interface SuggestResult {
  suggestions: Suggestion[];
  total: number;
}
