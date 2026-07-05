// frontend/src/components/layout/RightPanel.tsx
// 右栏：JD 分析卡片 + Gap 报告列表 + AI 生成预览区（空状态）
// US-4：JD 分析区域接入真实后端（analyzeJD），无结果时显示 JDUploadZone，
//       有结果时显示 JDCard + "重新分析"按钮。
// US-5：Gap 报告区域接入 GapReportView（基于 JD 结构化数据 + 知识库语义比对）。

import { useState } from 'react';
import JDUploadZone from '@/components/jd/JDUploadZone';
import JDCard from '@/components/jd/JDCard';
import GapReportView from '@/components/gap/GapReportView';
import GenerateView from '@/components/generate/GenerateView';
import type { JDAnalysisResult } from '@/types/jd';

interface RightPanelProps {
  /** US-8：AI 生成的简历数据（用于联动，由 MainLayout 提升） */
  resumeData?: Record<string, unknown> | null;
  /** US-8：AI 生成成功回调，把结果传回 MainLayout */
  onResumeGenerated?: (data: Record<string, unknown>) => void;
  /** US-8：当前选中的模板 id，用于导出 PDF */
  templateId?: string;
}

export default function RightPanel({
  onResumeGenerated,
  templateId,
}: RightPanelProps) {
  // JD 分析结果（US-4）：null 时显示上传区，非 null 时显示 JDCard
  const [jdResult, setJdResult] = useState<JDAnalysisResult | null>(null);

  function handleJDAnalyzed(result: JDAnalysisResult) {
    setJdResult(result);
  }

  function handleReset() {
    setJdResult(null);
  }

  return (
    <aside
      className="flex flex-col overflow-y-auto bg-bg-secondary border-l border-border-default"
      style={{ width: 'var(--right-panel-width)', minWidth: 'var(--right-panel-width)' }}
    >
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
            <JDCard result={jdResult} />
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
        <GapReportView structuredJD={(jdResult?.structured ?? null) as Record<string, unknown> | null} />
      </section>

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
        />
      </section>
    </aside>
  );
}
