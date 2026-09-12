// frontend/src/components/layout/RightPanel.tsx
// 右栏：JD 分析卡片 + Gap 报告列表 + AI 生成预览区（空状态）
// US-4：JD 分析区域接入真实后端（analyzeJD），无结果时显示 JDUploadZone，
//       有结果时显示 JDCard + "重新分析"按钮。
// US-5：Gap 报告区域接入 GapReportView（基于 JD 结构化数据 + 知识库语义比对）。

import { useCallback, useState } from 'react';
import JDUploadZone from '@/components/jd/JDUploadZone';
import JDCard from '@/components/jd/JDCard';
import GapReportView from '@/components/gap/GapReportView';
import TutorView from '@/components/tutor/TutorView';
import GenerateView from '@/components/generate/GenerateView';
import type { JDAnalysisResult } from '@/types/jd';
import type { GapReport } from '@/types/gap';
import type { ResumeNode } from '@/types/tree';

interface RightPanelProps {
  /** US-8：AI 生成的简历数据（用于联动，由 MainLayout 提升） */
  resumeData?: Record<string, unknown> | null;
  /** US-8：AI 生成成功回调，把结果传回 MainLayout */
  onResumeGenerated?: (data: Record<string, unknown>) => void;
  /** US-8：当前选中的模板 id，用于导出 PDF */
  templateId?: string;
  /** US-10：版本树节点列表，用于"保存到节点"功能 */
  treeNodes?: ResumeNode[];
  /** US-14: JD 分析成功后通知 MainLayout（用于一键生成） */
  onJDAnalyzed?: (structuredJD: Record<string, unknown> | null) => void;
  /** US-29：Gap 报告提升到 MainLayout（供 AI 快捷指令组装上下文） */
  gapReport: GapReport | null;
  onGapReport: (report: GapReport | null) => void;
  /** US-29：AI 快捷指令入口（带工作台上下文发起对话） */
  onQuickAsk: (prompt: string) => void;
  /** 收起右栏回调 */
  onCollapse?: () => void;
}

/** US-29：PRD 验收场景的固定快捷指令 */
const QUICK_PROMPTS: { label: string; prompt: string }[] = [
  {
    label: '针对当前 JD 优化选中节点',
    prompt: '帮我针对已上传的 JD 优化当前选中节点的项目经历，基于知识库素材，不要编造。',
  },
  {
    label: '我的经历太少怎么办',
    prompt: '对照我的知识库素材和已上传的 JD，分析我的经历太少的问题，并给出可补充的方向。',
  },
  {
    label: '把选中节点改得更量化',
    prompt: '把当前选中节点的内容改得更量化：为每条经历补充可验证的数字，缺的先问我，不要编造。',
  },
];

export default function RightPanel({
  onResumeGenerated,
  templateId,
  treeNodes,
  onJDAnalyzed,
  gapReport,
  onGapReport,
  onQuickAsk,
  onCollapse,
}: RightPanelProps) {
  // JD 分析结果（US-4）：null 时显示上传区，非 null 时显示 JDCard
  const [jdResult, setJdResult] = useState<JDAnalysisResult | null>(null);
  // US-29：自定义快捷指令输入
  const [customPrompt, setCustomPrompt] = useState('');

  function handleJDAnalyzed(result: JDAnalysisResult) {
    setJdResult(result);
    onGapReport(null); // 重新分析 JD 时重置 Gap 报告
    onJDAnalyzed?.(result.structured ? { ...result.structured } : null);
  }

  const handleStructuredChange = useCallback((structured: JDAnalysisResult['structured']) => {
    onJDAnalyzed?.({ ...structured });
  }, [onJDAnalyzed]);

  function handleReset() {
    setJdResult(null);
    onGapReport(null);
    onJDAnalyzed?.(null);
  }

  function handleCustomSubmit() {
    const text = customPrompt.trim();
    if (!text) return;
    onQuickAsk(text);
    setCustomPrompt('');
  }

  return (
    <aside
      className="flex flex-col overflow-y-auto bg-bg-secondary border-l border-border-default relative"
      style={{ width: 'var(--right-panel-width)', minWidth: 'var(--right-panel-width)' }}
    >
      {/* 收起按钮 — 固定在右上角 */}
      {onCollapse && (
        <button
          onClick={onCollapse}
          className="absolute top-2 right-2 z-10 w-6 h-6 flex items-center justify-center rounded-md text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors cursor-pointer"
          title="收起右栏"
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M10 2L4 8l6 6" />
          </svg>
        </button>
      )}

      {/* Section 1: JD 分析 */}
      <section className="border-b border-border-subtle p-4">
        <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-text-primary">
          <svg
            className="w-4 h-4 opacity-70"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{ color: 'var(--color-node-company)' }}
          >
            <rect x="2" y="3" width="12" height="10" rx="1.5" />
            <path d="M2 6h12" />
            <circle cx="11" cy="9" r="1.5" />
          </svg>
          职位截图分析
        </div>

        {/* 无分析结果：上传区；有结果：结构化卡片 + 重新分析 */}
        {jdResult ? (
          <div className="flex flex-col gap-2">
            <JDCard result={jdResult} onStructuredChange={handleStructuredChange} />
            <button
              type="button"
              onClick={handleReset}
              className="self-start text-xs px-3 py-1.5 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer transition-all hover:border-brand-primary hover:text-brand-primary font-body"
            >
              重新分析
            </button>
          </div>
        ) : (
          <JDUploadZone onAnalyzed={handleJDAnalyzed} />
        )}
      </section>

      {/* Section 2: Gap 报告 */}
      <section className="border-b border-border-subtle p-4">
        <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-text-primary">
          <svg
            className="w-4 h-4 opacity-70"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{ color: 'var(--state-warning)' }}
          >
            <path d="M8 1.5a6.5 6.5 0 0 0-6.5 6.5c0 2.5 1.5 4.5 3 5.8.5.4.8 1 .8 1.7v.5h5v-.5c0-.7.3-1.3.8-1.7 1.5-1.3 3-3.3 3-5.8A6.5 6.5 0 0 0 8 1.5z" />
            <line x1="5.5" y1="16" x2="10.5" y2="16" />
            <path d="M8 5v4M8 11.5v.5" />
          </svg>
          知识盲区报告
        </div>
        <GapReportView
          structuredJD={(jdResult?.structured ?? null) as Record<string, unknown> | null}
          onReport={onGapReport}
        />
      </section>

      {/* Section 2.7: AI 快捷指令（US-29 对话式工作台入口） */}
      <section className="border-b border-border-subtle p-4">
        <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-text-primary">
          <svg
            className="w-4 h-4 opacity-70"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{ color: 'var(--color-brand-primary)' }}
          >
            <path d="M14 7.5c0 3-2.7 5.5-6 5.5-.7 0-1.4-.1-2-.3L2 14l1-3.2c-.6-.9-1-2-1-3.3 0-3 2.7-5.5 6-5.5s6 2.5 6 5.5z" />
          </svg>
          AI 快捷指令
        </div>
        <div className="flex flex-col gap-1.5">
          {QUICK_PROMPTS.map((qp) => (
            <button
              key={qp.label}
              type="button"
              onClick={() => onQuickAsk(qp.prompt)}
              className="text-left text-xs px-3 py-2 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer transition-all duration-200 hover:border-brand-primary hover:text-brand-primary hover:translate-x-0.5 font-body"
            >
              {qp.label}
            </button>
          ))}
          <div className="flex gap-1.5 mt-1">
            <input
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCustomSubmit()}
              placeholder="自定义问题…"
              className="flex-1 min-w-0 text-xs px-2.5 py-2 rounded-md border border-border-default bg-bg-elevated text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-brand-primary transition-colors duration-200 font-body"
            />
            <button
              type="button"
              onClick={handleCustomSubmit}
              disabled={!customPrompt.trim()}
              className="text-xs px-2.5 py-2 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer transition-all duration-200 hover:border-brand-primary hover:text-brand-primary disabled:opacity-40 disabled:cursor-not-allowed font-body"
              title="发给 AI 助手"
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M2 8l12-5-5 12-2-5-5-2z" />
              </svg>
            </button>
          </div>
        </div>
      </section>

      {/* Section 2.5: AI 导师学习建议（US-11） */}
      {gapReport && (
        <section className="border-b border-border-subtle p-4">
          <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-text-primary">
            <svg
              className="w-4 h-4 opacity-70"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              style={{ color: 'var(--color-brand-primary)' }}
            >
              <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
              <path d="M8 5v3l2 2" />
            </svg>
            AI 导师学习建议
          </div>
          <TutorView gapItems={gapReport.items} />
        </section>
      )}

      {/* Section 3: AI 生成预览区 */}
      <section className="p-4">
        <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-text-primary">
          <svg
            className="w-4 h-4 opacity-70"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{ color: 'var(--color-brand-primary)' }}
          >
            <path d="M12 10V5a4 4 0 1 0-8 0v5" />
            <rect x="1" y="10" width="14" height="4" rx="1.5" />
            <circle cx="5" cy="12" r="1" fill="currentColor" />
            <circle cx="11" cy="12" r="1" fill="currentColor" />
          </svg>
          AI 简历生成
        </div>
        <GenerateView
          structuredJD={(jdResult?.structured ?? null) as Record<string, unknown> | null}
          onResumeGenerated={onResumeGenerated}
          templateId={templateId}
          treeNodes={treeNodes}
        />
      </section>
    </aside>
  );
}
