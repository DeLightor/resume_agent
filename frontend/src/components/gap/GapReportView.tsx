// frontend/src/components/gap/GapReportView.tsx
// 技能 Gap 报告（US-5）
// - 匹配度圆环 + 三色汇总
// - 技能详情列表（含状态徽章和描述）
// - 基于 JD 结构化数据 + 知识库语义比对

import { useState } from 'react';
import { generateGapReport } from '@/lib/api';
import type { GapReport, GapItem } from '@/types/gap';

interface GapReportViewProps {
  /** JD 结构化数据（来自 US-4 分析结果） */
  structuredJD: Record<string, unknown> | null;
  /** Gap 报告生成成功后回调（US-11：供 TutorView 使用） */
  onReport?: (report: GapReport) => void;
}

type Status = 'idle' | 'loading' | 'done' | 'error';

const STATUS_CONFIG: Record<string, { label: string; dotCls: string; badgeCls: string }> = {
  covered: {
    label: '已覆盖',
    dotCls: 'bg-success',
    badgeCls: 'bg-[rgba(5,150,105,0.08)] text-success',
  },
  partial: {
    label: '部分缺口',
    dotCls: 'bg-warning',
    badgeCls: 'bg-[rgba(217,119,6,0.08)] text-warning',
  },
  missing: {
    label: '未涉及',
    dotCls: 'bg-error',
    badgeCls: 'bg-[rgba(220,38,38,0.08)] text-error',
  },
};

const CATEGORY_LABELS: Record<string, string> = {
  tech_stack: '技术栈',
  hard_skills: '硬技能',
  soft_skills: '软技能',
  bonus_items: '加分项',
};

/** SVG 圆环进度条 */
function ScoreRing({ score }: { score: number }) {
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 70 ? 'var(--state-success)' : score >= 40 ? 'var(--state-warning)' : 'var(--state-error)';

  return (
    <div className="relative flex items-center justify-center" style={{ width: 72, height: 72 }}>
      <svg width="72" height="72" className="-rotate-90">
        <circle
          cx="36"
          cy="36"
          r={radius}
          fill="none"
          stroke="var(--color-border-default)"
          strokeWidth="5"
        />
        <circle
          cx="36"
          cy="36"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-lg font-bold text-text-primary" style={{ fontFamily: 'var(--font-mono)' }}>
          {score}
        </span>
        <span className="text-[9px] text-text-muted">匹配度</span>
      </div>
    </div>
  );
}

export default function GapReportView({ structuredJD, onReport }: GapReportViewProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [report, setReport] = useState<GapReport | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleGenerate() {
    if (!structuredJD || status === 'loading') return;
    setStatus('loading');
    setErrorMsg(null);
    try {
      const result = await generateGapReport(structuredJD);
      setReport(result);
      setStatus('done');
      onReport?.(result);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : '生成报告失败');
    }
  }

  // 无 JD 数据
  if (!structuredJD) {
    return (
      <div className="text-center text-xs text-text-muted py-4">
        请先上传 JD 截图完成分析
      </div>
    );
  }

  // 生成中
  if (status === 'loading') {
    return (
      <div className="flex flex-col items-center gap-2 py-6">
        <svg
          className="animate-spin w-5 h-5"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          style={{ color: 'var(--color-brand-primary)' }}
        >
          <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
        </svg>
        <span className="text-xs text-text-secondary">正在比对知识库...</span>
      </div>
    );
  }

  // 错误
  if (status === 'error') {
    return (
      <div className="space-y-2">
        <div className="text-xs text-error">{errorMsg}</div>
        <button
          onClick={handleGenerate}
          className="text-xs px-3 py-1.5 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer hover:border-brand-primary hover:text-brand-primary transition-all"
        >
          重试
        </button>
      </div>
    );
  }

  // 空闲状态（未生成）
  if (status === 'idle' || !report) {
    return (
      <button
        onClick={handleGenerate}
        className="w-full text-xs px-3 py-2 rounded-md bg-brand-primary text-white font-medium cursor-pointer hover:opacity-90 transition-opacity"
      >
        生成 Gap 报告
      </button>
    );
  }

  // 已生成报告
  const { overall_score, summary, items } = report;

  return (
    <div className="space-y-3">
      {/* 圆环 + 汇总 */}
      <div className="flex items-center gap-3">
        <ScoreRing score={overall_score} />
        <div className="flex-1 space-y-1">
          {[
            { key: 'covered', label: '已覆盖', count: summary.covered, cls: 'text-success' },
            { key: 'partial', label: '部分缺口', count: summary.partial, cls: 'text-warning' },
            { key: 'missing', label: '未涉及', count: summary.missing, cls: 'text-error' },
          ].map((s) => (
            <div key={s.key} className="flex items-center gap-2 text-xs">
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS_CONFIG[s.key].dotCls}`} />
              <span className="text-text-secondary">{s.label}</span>
              <span className={`font-mono font-semibold ${s.cls}`}>{s.count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 技能列表 */}
      <div className="space-y-1.5">
        {items.map((item: GapItem) => {
          const cfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.missing;
          return (
            <div
              key={`${item.skill}-${item.category}`}
              className="flex items-start gap-2 py-1.5 border-b border-border-subtle last:border-b-0"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-text-primary truncate">
                    {item.skill}
                  </span>
                  <span className="text-[9px] text-text-muted bg-bg-tertiary px-1 py-0.5 rounded flex-shrink-0">
                    {CATEGORY_LABELS[item.category] || item.category}
                  </span>
                </div>
                <div className="text-xs text-text-tertiary leading-tight mt-0.5">
                  {item.description}
                </div>
              </div>
              <span
                className={`text-[10px] px-2 py-px rounded-full font-medium whitespace-nowrap flex-shrink-0 ${cfg.badgeCls}`}
              >
                {cfg.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* 重新生成按钮 */}
      <button
        onClick={handleGenerate}
        className="w-full text-xs px-3 py-1.5 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer hover:border-brand-primary hover:text-brand-primary transition-all"
      >
        重新生成
      </button>
    </div>
  );
}
