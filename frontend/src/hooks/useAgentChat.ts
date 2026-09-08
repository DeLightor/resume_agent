// frontend/src/hooks/useAgentChat.ts
// Agent 对话状态管理（US-28 agent-sse-stream Task 4.1）
//
// 职责：会话列表/切换、SSE 发送、事件累积、断线恢复（refetch + 轮询）。
// 时间线 UI 渲染由 AgentWorkbench 消费本 hook 的状态。

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createAgentSession,
  getAgentSession,
  listAgentSessions,
  streamAgentChat,
  StreamConnectError,
} from '@/lib/api';
import type {
  AgentEvent,
  AgentSessionSummary,
} from '@/types/agent';

/** 用户消息事件（本地回显，不来自 SSE 协议） */
export interface UserMessageEvent {
  type: 'user_message';
  text: string;
}

/** 历史会话回放的 assistant 消息（本地构造，不来自 SSE 协议） */
export interface AssistantMessageEvent {
  type: 'assistant_message';
  text: string;
}

/** agent-write-guard: 待确认写入的 UI 视图（SSE 事件与详情回放共用） */
export interface PendingWriteView {
  node_id: string;
  content: unknown;
}

/** 时间线渲染事件：SSE 事件 + 本地回放消息 */
export type TimelineEvent = AgentEvent | UserMessageEvent | AssistantMessageEvent;

/** 单条时间线渲染单元（事件 + 本地时间戳） */
export interface TimelineItem {
  id: number;
  event: TimelineEvent;
  ts: number;
}

export type ChatPhase = 'idle' | 'streaming' | 'reconnecting';

export interface UseAgentChat {
  /** 历史会话列表（新→旧） */
  sessions: AgentSessionSummary[];
  /** 当前会话 id（null = 未创建/未选择） */
  activeSessionId: string | null;
  /** 当前会话状态（服务端权威值，随 done 事件更新） */
  sessionStatus: string | null;
  /** 本轮时间线（新→旧渲染时 reverse） */
  timeline: TimelineItem[];
  /** Agent 待回答的问题（awaiting_user 时非空） */
  pendingQuestion: string | null;
  /** agent-write-guard: 待确认写入（写入门禁暂停时非空） */
  pendingWrite: PendingWriteView | null;
  /** 最终回复（done 事件的 final_message） */
  finalMessage: string | null;
  /** 运行相位 */
  phase: ChatPhase;
  /** 流式/网络错误信息 */
  error: string | null;
  /** 当前会话绑定的上下文（创建/更新时记录，用于状态条显示） */
  sessionContext: Record<string, unknown> | null;
  /** 新建会话（US-29：可带初始上下文） */
  newSession: (context?: Record<string, unknown>) => Promise<void>;
  /** 切换历史会话（恢复视图） */
  selectSession: (sessionId: string) => Promise<void>;
  /** 发送消息（或回答 ask_user）；返回是否真正发出 */
  send: (message: string) => Promise<boolean>;
}

/** useAgentChat 参数（US-29） */
export interface UseAgentChatArgs {
  /**
   * 工作台上下文提供者：每次 send 时调用取最新值
   * （当前节点/JD/Gap 摘要），服务端幂等去重，未变化不重复注入。
   */
  getContext?: () => Record<string, unknown>;
}

/** 断线后轮询会话详情的间隔 */
const RECONNECT_POLL_MS = 2000;
/** 恢复轮询上限（30 × 2s = 60s），超时提示用户稍后查看 */
const RECONNECT_MAX_ATTEMPTS = 30;

export function useAgentChat(args?: UseAgentChatArgs): UseAgentChat {
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [pendingWrite, setPendingWrite] = useState<PendingWriteView | null>(null);
  const [finalMessage, setFinalMessage] = useState<string | null>(null);
  const [phase, setPhase] = useState<ChatPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [sessionContext, setSessionContext] = useState<
    Record<string, unknown> | null
  >(null);

  const nextId = useRef(1);
  const abortRef = useRef<AbortController | null>(null);
  const creatingRef = useRef(false);
  /** 当前活跃会话（供 recover 轮询检测会话切换） */
  const activeIdRef = useRef<string | null>(null);
  /** 上下文提供者（ref 保持最新，避免 send 依赖重建） */
  const getContextRef = useRef(args?.getContext);
  getContextRef.current = args?.getContext;

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await listAgentSessions());
    } catch {
      /* 列表失败不阻塞主流程 */
    }
  }, []);

  // 挂载时拉取历史会话列表
  useEffect(() => {
    void refreshSessions();
    return () => abortRef.current?.abort();
  }, [refreshSessions]);

  const appendEvent = useCallback((event: AgentEvent) => {
    setTimeline((prev) => [
      ...prev,
      { id: nextId.current++, event, ts: Date.now() },
    ]);
  }, []);

  const handleEvent = useCallback((event: AgentEvent) => {
    appendEvent(event);
    switch (event.type) {
      case 'ask_user':
        setPendingQuestion(event.question);
        setPendingWrite(null);
        break;
      case 'write_confirm':
        setPendingWrite({ node_id: event.node_id, content: event.content });
        break;
      case 'done':
        setSessionStatus(event.status);
        if (event.status === 'awaiting_user' && event.pending_question) {
          setPendingQuestion(event.pending_question);
        } else {
          setPendingQuestion(null);
          setPendingWrite(null);
        }
        if (event.final_message != null) setFinalMessage(event.final_message);
        break;
      case 'error':
        setSessionStatus('failed');
        // 错误详情由时间线 error 事件渲染（避免与底部 error 文字双重显示）
        break;
      default:
        break;
    }
  }, [appendEvent]);

  /** 断线恢复：refetch 会话详情；running 则轮询至终态 */
  const recover = useCallback(
    async (sessionId: string) => {
      setPhase('reconnecting');
      for (let attempt = 0; attempt < RECONNECT_MAX_ATTEMPTS; attempt++) {
        // 用户已切换会话：放弃旧会话的恢复
        if (activeIdRef.current !== sessionId) {
          setPhase('idle');
          return;
        }
        try {
          const detail = await getAgentSession(sessionId);
          setSessionStatus(detail.status);
          if (detail.status !== 'running') {
            setPendingQuestion(detail.pending_question);
            setPendingWrite(
              detail.pending_write
                ? {
                    node_id: detail.pending_write.node_id,
                    content: detail.pending_write.content,
                  }
                : null,
            );
            const last = detail.messages[detail.messages.length - 1];
            if (last?.role === 'assistant' && last.content) {
              setFinalMessage(last.content);
            }
            setPhase('idle');
            return;
          }
        } catch {
          /* 网络仍断开，继续轮询 */
        }
        await new Promise((r) => setTimeout(r, RECONNECT_POLL_MS));
      }
      // 超时放弃：后台可能仍在收敛，提示用户稍后从会话列表查看
      setPhase('idle');
      setError('连接恢复超时。若会话仍在后台运行，稍后可从左侧列表切换回来查看结果。');
    },
    [],
  );

  const newSession = useCallback(async (context?: Record<string, unknown>) => {
    // StrictMode 双挂载 / 连点保护：避免创建两个会话
    if (creatingRef.current) return;
    creatingRef.current = true;
    try {
      abortRef.current?.abort();
      const created = await createAgentSession(context ?? {});
      setActiveSessionId(created.id);
      activeIdRef.current = created.id;
      setSessionStatus(created.status);
      setSessionContext(context ?? null);
      setTimeline([]);
      setPendingQuestion(null);
      setPendingWrite(null);
      setFinalMessage(null);
      setError(null);
      setPhase('idle');
      void refreshSessions();
    } catch (err) {
      // 创建失败必须可见（否则输入框一直禁用且无提示）
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      creatingRef.current = false;
    }
  }, [refreshSessions]);

  const selectSession = useCallback(
    async (sessionId: string) => {
      abortRef.current?.abort();
      const detail = await getAgentSession(sessionId);
      setActiveSessionId(sessionId);
      activeIdRef.current = sessionId;
      setSessionStatus(detail.status);
      setSessionContext(detail.context ?? null);
      setPendingQuestion(detail.pending_question);
      setPendingWrite(
        detail.pending_write
          ? { node_id: detail.pending_write.node_id, content: detail.pending_write.content }
          : null,
      );
      const last = detail.messages[detail.messages.length - 1];
      setFinalMessage(last?.role === 'assistant' ? last.content : null);
      // US-29：回放对话历史（用户气泡 + assistant 回复），
      // 工具轨迹不重放（原文案保留，traces 端点可后续按需展示）
      const rebuilt: TimelineItem[] = [];
      for (const m of detail.messages) {
        if (m.role === 'user' && m.content) {
          rebuilt.push({
            id: nextId.current++,
            event: { type: 'user_message', text: m.content },
            ts: 0,
          });
        } else if (m.role === 'assistant' && m.content) {
          rebuilt.push({
            id: nextId.current++,
            event: { type: 'assistant_message', text: m.content },
            ts: 0,
          });
        }
      }
      setTimeline(rebuilt);
      setError(null);
      setPhase('idle');
    },
    [],
  );

  const send = useCallback(
    async (message: string): Promise<boolean> => {
      // 用 ref 读最新会话 id（pendingAsk 流程中 newSession 刚完成时，
      // 本闭包捕获的 activeSessionId 可能还是 null —— stale closure）
      const sessionId = activeIdRef.current;
      if (!sessionId || !message.trim() || phase === 'streaming') {
        return false;
      }

      // 立即回显用户消息（不等 SSE，发送后立即可见）
      setTimeline((prev) => [
        ...prev,
        {
          id: nextId.current++,
          event: { type: 'user_message', text: message.trim() },
          ts: Date.now(),
        },
      ]);
      setPendingQuestion(null);
      setPendingWrite(null);

      const controller = new AbortController();
      abortRef.current = controller;
      setPhase('streaming');
      setFinalMessage(null);
      setError(null);

      try {
        await streamAgentChat(sessionId, message, {
          signal: controller.signal,
          onEvent: handleEvent,
          // US-29：每次发送携带最新工作台上下文（服务端幂等去重）
          context: getContextRef.current?.(),
        });
        setPhase('idle');
        setSessionContext(getContextRef.current?.() ?? null);
        void refreshSessions();
      } catch (err) {
        // 用户主动取消不算错误
        if (controller.signal.aborted) {
          setPhase('idle');
          return true;
        }
        setError(err instanceof Error ? err.message : String(err));
        if (err instanceof StreamConnectError) {
          // 流未建立：服务端没有后台任务在跑，无需恢复轮询
          setPhase('idle');
        } else {
          // 流中断：后台仍在跑，走恢复路径
          await recover(sessionId);
        }
      }
      return true;
    },
    [phase, handleEvent, recover, refreshSessions],
  );

  return {
    sessions,
    activeSessionId,
    sessionStatus,
    timeline,
    pendingQuestion,
    pendingWrite,
    finalMessage,
    phase,
    error,
    sessionContext,
    newSession,
    selectSession,
    send,
  };
}
