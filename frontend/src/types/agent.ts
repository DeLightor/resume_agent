// frontend/src/types/agent.ts
// Agent 会话与 SSE 事件类型（US-28 agent-sse-stream，对齐 design.md §2 事件协议）

/** 会话状态机：running → awaiting_user / done / failed */
export type AgentSessionStatus = 'running' | 'awaiting_user' | 'done' | 'failed';

/** 会话摘要（GET /api/agent/sessions 列表项，不含 messages） */
export interface AgentSessionSummary {
  id: string;
  status: AgentSessionStatus;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** 会话消息（OpenAI 协议格式：system / user / assistant / tool） */
export interface AgentMessage {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  tool_call_id?: string;
  tool_calls?: {
    id: string;
    type: 'function';
    function: { name: string; arguments: string };
  }[];
}

/** 会话详情（GET /api/agent/sessions/{id}） */
export interface AgentSessionDetail extends AgentSessionSummary {
  messages: AgentMessage[];
  pending_question: string | null;
}

/** SSE 事件载荷（event 帧的 data JSON） */
export type AgentEvent =
  | { type: 'thinking'; round: number }
  | {
      type: 'tool_call';
      round: number;
      tool_call_id: string;
      name: string;
      arguments: Record<string, unknown>;
    }
  | {
      type: 'tool_result';
      round: number;
      tool_call_id: string;
      name: string;
      result: unknown;
    }
  | { type: 'ask_user'; question: string }
  | {
      type: 'done';
      status: AgentSessionStatus;
      final_message?: string;
      pending_question?: string;
      rounds_used?: number;
    }
  | { type: 'error'; message: string; rounds_used?: number }
  /** 预留 US-30 Reviewer 双审 */
  | { type: 'review'; [key: string]: unknown }
  /** 预留 US-30 草稿事件 */
  | { type: 'draft'; [key: string]: unknown };
