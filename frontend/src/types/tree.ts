// frontend/src/types/tree.ts

export type NodeType = 'master' | 'branch' | 'company';

export interface ResumeNode {
  id: string;
  node_id: string;
  parent_id: string | null;
  node_type: NodeType;
  title: string;
  company?: string | null;
  direction?: string | null;
  /** 节点结构化简历内容（GET /api/tree/{node_id} 返回时填充） */
  content_json?: Record<string, unknown> | null;
  /** US-17: 是否有上游 personal_info 变更待合并 */
  has_upstream_update?: boolean;
}

export interface TreeEdge {
  source: string;
  target: string;
}

export interface TreeData {
  nodes: ResumeNode[];
  edges: TreeEdge[];
}

/** API 统一响应格式 */
export interface ApiResponse<T> {
  ok: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
}

/** POST /api/tree/node 请求体 */
export interface CreateNodeRequest {
  parent_id: string;
  node_type: NodeType;
  title: string;
  company?: string;
  direction?: string;
}

/** PUT /api/tree/node/{node_id} 请求体 */
export interface UpdateNodeRequest {
  title?: string;
  content_json?: Record<string, unknown>;
}
