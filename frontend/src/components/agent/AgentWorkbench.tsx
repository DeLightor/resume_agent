// frontend/src/components/agent/AgentWorkbench.tsx
// AI 助手工作台（US-28 agent-sse-stream Task 4.2）
//
// 三区布局：左侧会话列表 / 中间行为时间线（工具调用可展开入参出参）/
// 底部输入区。ask_user 暂停时时间线内嵌问题卡片。
// 状态管理见 hooks/useAgentChat。

import { useEffect, useRef, useState } from 'react';
import { useAgentChat } from '@/hooks/useAgentChat';
import type { TimelineItem } from '@/hooks/useAgentChat';
import type { TimelineEvent } from '@/hooks/useAgentChat';

/** 事件类型的图标与标题 */
function eventTitle(event: TimelineEvent): string {
  switch (event.type) {
    case 'thinking':
      return `思考中（第 ${event.round} 轮）`;
    case 'tool_call':
      return `调用工具 ${event.name}`;
    case 'tool_result':
      return `工具返回 ${event.name}`;
    case 'ask_user':
      return '需要你的输入';
    case 'done':
      return event.status === 'awaiting_user' ? '等待你的回答' : '完成';
    case 'error':
      return '出错了';
    case 'assistant_message':
      return 'AI 回复';
    default:
      return event.type;
  }
}

/** 事件类型的左侧圆点颜色（tailwind 任意值引用设计令牌） */
function eventDotCls(event: TimelineEvent): string {
  switch (event.type) {
    case 'thinking':
      return 'bg-text-muted';
    case 'tool_call':
      return 'bg-brand-primary';
    case 'tool_result':
      return 'bg-brand-primary';
    case 'ask_user':
      return 'bg-amber-500';
    case 'done':
      return 'bg-emerald-500';
    case 'error':
      return 'bg-red-500';
    default:
      return 'bg-text-muted';
  }
}

/** JSON 等宽渲染（入参/出参） */
function JsonBlock({ data }: { data: unknown }) {
  return (
    <pre className="text-xs font-mono text-text-secondary bg-bg-tertiary rounded-md p-2 overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap break-all">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

/** 工具调用条目：可展开入参出参 */
function ToolTimelineItem({
  item,
  hasResult,
}: {
  item: TimelineItem;
  hasResult: boolean;
}) {
  const [open, setOpen] = useState(false);
  const event = item.event;
  if (event.type !== 'tool_call' && event.type !== 'tool_result') return null;

  const isCall = event.type === 'tool_call';
  return (
    <div className="timeline-item">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 text-left w-full cursor-pointer border-none bg-transparent p-0 hover:text-brand-primary transition-colors duration-200"
      >
        <span className={`w-2 h-2 rounded-full shrink-0 ${eventDotCls(event)}`} />
        <span className="text-sm font-medium">
          {eventTitle(event)}
          {!isCall && !hasResult ? '（失败）' : ''}
        </span>
        <span className="text-xs text-text-muted font-mono ml-auto">
          {isCall ? `#${event.round}` : ''}
        </span>
        <span className="text-xs text-text-muted">{open ? '收起 ▲' : '展开 ▼'}</span>
      </button>
      {open && (
        <div className="mt-2 ml-4 flex flex-col gap-2">
          {isCall && <JsonBlock data={event.arguments} />}
          {!isCall && <JsonBlock data={event.result} />}
        </div>
      )}
    </div>
  );
}

/** 用户消息：右侧品牌色气泡，发送后立即回显 */
function UserTimelineItem({ text }: { text: string }) {
  return (
    <div className="timeline-item flex justify-end">
      <div className="max-w-[80%] rounded-lg bg-brand-primary text-white px-3 py-2 text-sm whitespace-pre-wrap break-words">
        {text}
      </div>
    </div>
  );
}

/** 普通时间线条目（thinking / ask_user / done / error / 历史回放） */
function SimpleTimelineItem({ item }: { item: TimelineItem }) {
  const event = item.event;
  let body: React.ReactNode = null;
  if (event.type === 'ask_user' || (event.type === 'done' && event.status === 'awaiting_user')) {
    body = (
      <p className="text-sm text-text-primary mt-1 ml-4">
        {event.type === 'ask_user' ? event.question : event.pending_question}
      </p>
    );
  } else if (event.type === 'assistant_message') {
    // US-29：历史会话回放的 assistant 消息
    body = (
      <p className="text-sm text-text-primary mt-1 ml-4 whitespace-pre-wrap leading-relaxed">
        {event.text}
      </p>
    );
  } else if (event.type === 'done' && event.final_message) {
    body = (
      <p className="text-sm text-text-primary mt-1 ml-4 whitespace-pre-wrap leading-relaxed">
        {event.final_message}
      </p>
    );
  } else if (event.type === 'error') {
    body = (
      <p className="text-sm text-red-600 mt-1 ml-4">{event.message}</p>
    );
  }
  return (
    <div className="timeline-item">
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full shrink-0 ${eventDotCls(event)}`} />
        <span className="text-sm font-medium">{eventTitle(event)}</span>
        {event.type === 'thinking' && (
          <span className="flex gap-1">
            <span className="thinking-dot" />
            <span className="thinking-dot" style={{ animationDelay: '0.2s' }} />
            <span className="thinking-dot" style={{ animationDelay: '0.4s' }} />
          </span>
        )}
      </div>
      {body}
    </div>
  );
}

export interface AgentWorkbenchProps {
  /** US-29：工作台上下文提供者（send 时携带，服务端幂等去重） */
  agentContext?: () => Record<string, unknown>;
  /** US-29：待自动发送的快捷指令（右栏入口触发，一次性消费） */
  pendingAsk?: { context: Record<string, unknown>; prompt: string } | null;
  /** US-29：快捷指令已被消费（清除 MainLayout 中的状态） */
  onPendingAskConsumed?: () => void;
}

/** US-29：从会话 context 生成状态条摘要 */
function contextSummary(ctx: Record<string, unknown> | null): string {
  if (!ctx || Object.keys(ctx).length === 0) return '无';
  const parts: string[] = [];
  if (typeof ctx.current_node_id === 'string') parts.push(`节点 ${ctx.current_node_id}`);
  const jd = ctx.structured_jd as Record<string, unknown> | undefined;
  if (typeof jd?.job_title === 'string' && jd.job_title) parts.push(`JD ${jd.job_title}`);
  const gap = ctx.gap_summary as Record<string, unknown> | undefined;
  if (gap && typeof gap.overall_score === 'number') {
    parts.push(`Gap ${Math.round(gap.overall_score * 100)}%`);
  }
  return parts.length > 0 ? parts.join(' · ') : '已附加';
}

export default function AgentWorkbench({
  agentContext,
  pendingAsk,
  onPendingAskConsumed,
}: AgentWorkbenchProps) {
  const {
    sessions,
    activeSessionId,
    sessionStatus,
    timeline,
    pendingQuestion,
    phase,
    error,
    sessionContext,
    newSession,
    selectSession,
    send,
  } = useAgentChat({ getContext: agentContext });

  const [input, setInput] = useState('');
  const [answer, setAnswer] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);
  /** pendingAsk 消费中防重入（创建会话是异步的） */
  const consumingAskRef = useRef(false);

  // 新事件到达时滚动到底部
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [timeline.length, pendingQuestion]);

  // 无会话时自动创建（pendingAsk 流程会自己创建带上下文的会话，避免竞态）
  useEffect(() => {
    if (!activeSessionId && !pendingAsk) void newSession();
  }, [activeSessionId, pendingAsk, newSession]);

  // US-29：消费快捷指令 → 创建带上下文的新会话 → 自动发送首条消息
  useEffect(() => {
    if (!pendingAsk || consumingAskRef.current) return;
    consumingAskRef.current = true;
    void (async () => {
      try {
        await newSession(pendingAsk.context);
        await send(pendingAsk.prompt);
      } finally {
        consumingAskRef.current = false;
        onPendingAskConsumed?.();
      }
    })();
  }, [pendingAsk, newSession, send, onPendingAskConsumed]);

  const busy = phase === 'streaming' || phase === 'reconnecting';

  return (
    <div className="h-full flex min-h-0">
      {/* 左：会话列表 */}
      <aside className="w-56 shrink-0 border-r border-border-default bg-bg-secondary flex flex-col">
        <div className="p-3">
          <button
            type="button"
            onClick={() => void newSession()}
            className="w-full px-3 py-1.5 rounded-md text-sm bg-brand-primary text-white border-none cursor-pointer hover:bg-brand-primary-hover transition-colors duration-200"
          >
            + 新对话
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-2 flex flex-col gap-1">
          {sessions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => void selectSession(s.id)}
              className={`text-left px-3 py-2 rounded-md text-xs cursor-pointer border-none transition-colors duration-200 ${
                s.id === activeSessionId
                  ? 'bg-brand-primary-muted text-brand-primary'
                  : 'text-text-secondary hover:bg-bg-hover'
              }`}
            >
              <span className="block truncate font-medium">
                {new Date(s.created_at).toLocaleString('zh-CN', {
                  month: 'numeric',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </span>
              <span className="flex items-center gap-1">
                <span className="text-text-muted">{s.status}</span>
                {/* US-29：带上下文的会话标记 */}
                {Object.keys(s.context ?? {}).length > 0 && (
                  <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-brand-primary-muted text-brand-primary shrink-0">
                    上下文
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      </aside>

      {/* 右：时间线 + 输入区 */}
      <div className="flex-1 flex flex-col min-w-0 bg-bg-primary">
        {/* 状态条 */}
        <div className="h-9 flex items-center gap-3 px-4 border-b border-border-default text-xs text-text-tertiary bg-bg-secondary shrink-0">
          <span>会话：{activeSessionId ? activeSessionId.slice(0, 8) : '—'}</span>
          <span>状态：{sessionStatus ?? '—'}</span>
          {/* US-29：当前会话绑定的上下文摘要 */}
          <span
            title={sessionContext ? JSON.stringify(sessionContext) : undefined}
            className="truncate max-w-72"
          >
            上下文：{contextSummary(sessionContext)}
          </span>
          {phase === 'streaming' && (
            <span className="text-brand-primary">● Agent 运行中</span>
          )}
          {phase === 'reconnecting' && (
            <span className="text-amber-600">● 连接中断，正在恢复…</span>
          )}
        </div>

        {/* 时间线 */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
          {timeline.length === 0 && (
            <p className="text-sm text-text-muted text-center mt-8">
              和 AI 助手聊聊吧——它可以检索知识库、分析 JD、帮你优化简历。
            </p>
          )}
          <div className="flex flex-col gap-3">
            {timeline.map((item) => {
              if (item.event.type === 'user_message') {
                return <UserTimelineItem key={item.id} text={item.event.text} />;
              }
              return item.event.type === 'tool_call' ||
                item.event.type === 'tool_result' ? (
                <ToolTimelineItem key={item.id} item={item} hasResult />
              ) : (
                <SimpleTimelineItem key={item.id} item={item} />
              );
            })}
          </div>

          {/* ask_user 回答卡片 */}
          {pendingQuestion && phase !== 'streaming' && (
            <div className="mt-4 ml-4 p-3 rounded-lg border border-amber-300 bg-amber-50">
              <p className="text-sm font-medium text-amber-800">
                {pendingQuestion}
              </p>
              <div className="flex gap-2 mt-2">
                <input
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && answer.trim()) {
                      void send(answer.trim()).then((ok) => {
                        if (ok) setAnswer('');
                      });
                    }
                  }}
                  placeholder="输入你的回答…"
                  className="flex-1 px-3 py-1.5 rounded-md text-sm border border-border-default focus:outline-none focus:border-brand-primary"
                />
                <button
                  type="button"
                  onClick={() => {
                    if (answer.trim()) {
                      void send(answer.trim()).then((ok) => {
                        if (ok) setAnswer('');
                      });
                    }
                  }}
                  className="px-3 py-1.5 rounded-md text-sm bg-brand-primary text-white border-none cursor-pointer hover:bg-brand-primary-hover transition-colors duration-200"
                >
                  回答
                </button>
              </div>
            </div>
          )}

          {error && (
            <p className="mt-3 text-xs text-red-600">{error}</p>
          )}
        </div>

        {/* 输入区 */}
        <div className="p-3 border-t border-border-default bg-bg-secondary shrink-0">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && input.trim() && !busy) {
                  void send(input.trim()).then((ok) => {
                    if (ok) setInput('');
                  });
                }
              }}
              disabled={busy || !activeSessionId}
              placeholder={
                busy ? 'Agent 处理中…' : '输入消息，如「分析我的技能和后端岗位的差距」'
              }
              className="flex-1 px-3 py-2 rounded-md text-sm border border-border-default focus:outline-none focus:border-brand-primary disabled:bg-bg-tertiary disabled:text-text-muted"
            />
            <button
              type="button"
              disabled={busy || !input.trim()}
              onClick={() => {
                void send(input.trim()).then((ok) => {
                  if (ok) setInput('');
                });
              }}
              className="px-4 py-2 rounded-md text-sm bg-brand-primary text-white border-none cursor-pointer hover:bg-brand-primary-hover transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              发送
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
