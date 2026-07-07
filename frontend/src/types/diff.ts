// frontend/src/types/diff.ts
// US-10：版本 Diff 对比类型定义

/** 单条差异项 */
export interface DiffItem {
  type: 'added' | 'removed' | 'modified';
  field: string;
  value?: unknown;
  old_value?: unknown;
  new_value?: unknown;
  details?: DiffItem[];
}

/** 三段差异 */
export interface DiffSections {
  experience: DiffItem[];
  projects: DiffItem[];
  skills: DiffItem[];
}

/** Diff 汇总统计 */
export interface DiffSummary {
  added: number;
  removed: number;
  modified: number;
}

/** Diff 响应 data */
export interface DiffResult {
  node_a: { node_id: string; title: string };
  node_b: { node_id: string; title: string };
  diffs: DiffSections;
  summary: DiffSummary;
}
