// frontend/src/components/generate/SuggestionCards.tsx
// AI 智能补全建议卡片（US-9）

import type { Suggestion } from '@/types/suggest';

interface SuggestionCardsProps {
  suggestions: Suggestion[];
  onAccept: (suggestion: Suggestion) => void;
  onDismiss: (index: number) => void;
}

/** 建议类型 → 中文标签 */
const TYPE_LABELS: Record<string, string> = {
  add_highlight: '补充亮点',
  add_detail: '补充详情',
  add_tech_stack: '补充技术栈',
  add_skill_context: '补充场景',
};

/** 建议类型 → 标签颜色 */
const TYPE_STYLES: Record<string, string> = {
  add_highlight: 'bg-[rgba(99,102,241,0.1)] text-brand-primary',
  add_detail: 'bg-[rgba(99,102,241,0.1)] text-brand-primary',
  add_tech_stack: 'bg-[rgba(16,185,129,0.1)] text-success',
  add_skill_context: 'bg-[rgba(217,119,6,0.1)] text-warning',
};

export default function SuggestionCards({
  suggestions,
  onAccept,
  onDismiss,
}: SuggestionCardsProps) {
  // 无建议时显示空状态
  if (suggestions.length === 0) {
    return (
      <div className="border border-border-subtle rounded-md p-2 text-center text-[11px] text-text-muted">
        暂无补全建议
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {/* 标题行 */}
      <div className="flex items-center gap-1.5">
        <svg
          width="13"
          height="13"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="text-warning flex-shrink-0"
        >
          <path d="M8 1.5a4.5 4.5 0 0 0-2.5 8.3v1.2a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1V9.8A4.5 4.5 0 0 0 8 1.5z" />
          <path d="M6.5 13.5h3" />
          <path d="M7 15h2" />
        </svg>
        <span className="text-xs font-medium text-text-primary">智能补全建议</span>
        <span className="text-[10px] text-text-muted">({suggestions.length})</span>
      </div>

      {/* 建议卡片列表 */}
      <div className="space-y-1.5">
        {suggestions.map((s, i) => {
          const label = TYPE_LABELS[s.type] ?? s.type;
          const badgeClass = TYPE_STYLES[s.type] ?? 'bg-bg-tertiary text-text-secondary';

          return (
            <div
              key={`${s.field}-${i}`}
              className="border border-border-subtle rounded-md p-2 space-y-1"
            >
              {/* 顶部：类型标签 + 字段 */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${badgeClass}`}
                >
                  {label}
                </span>
                <span className="text-[10px] text-text-muted font-mono">
                  {s.field}
                </span>
              </div>

              {/* 中部：建议文本 */}
              <div className="text-xs text-text-primary leading-relaxed">
                {s.suggested_text}
              </div>

              {/* 底部：原因 + 来源 */}
              <div className="space-y-0.5">
                {s.reason && (
                  <div className="text-[10px] text-text-secondary">
                    <span className="text-text-muted">原因：</span>
                    {s.reason}
                  </div>
                )}
                {s.source && (
                  <div className="text-[10px] text-text-muted">
                    <span>来源：</span>
                    {s.source}
                  </div>
                )}
              </div>

              {/* 操作按钮 */}
              <div className="flex gap-1.5 pt-0.5">
                <button
                  onClick={() => onAccept(s)}
                  className="text-[11px] px-2 py-1 rounded bg-success text-white font-medium cursor-pointer hover:opacity-90 transition-opacity"
                >
                  采纳
                </button>
                <button
                  onClick={() => onDismiss(i)}
                  className="text-[11px] px-2 py-1 rounded border border-border-default text-text-tertiary bg-bg-elevated cursor-pointer hover:border-text-secondary hover:text-text-secondary transition-all"
                >
                  忽略
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
