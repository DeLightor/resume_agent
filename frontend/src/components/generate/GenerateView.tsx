// frontend/src/components/generate/GenerateView.tsx
// AI 简历生成（US-6）
// 检索 → 反思 → 撰写 3 步工作流

import { useState } from 'react';
import { exportResumePDF, generateResume } from '@/lib/api';
import type { GenerateResult } from '@/types/generate';

interface GenerateViewProps {
  structuredJD: Record<string, unknown> | null;
  gapReport?: Record<string, unknown> | null;
  /** US-8：生成成功后回调，把结果传给 MainLayout 供中栏预览 */
  onResumeGenerated?: (data: Record<string, unknown>) => void;
  /** US-8：当前选中的模板 id，用于导出 PDF */
  templateId?: string;
}

type Status = 'idle' | 'loading' | 'done' | 'error';
type Section = 'experience' | 'projects' | 'skills';

const SECTIONS: { key: Section; label: string; icon: string }[] = [
  { key: 'experience', label: '工作经历', icon: 'M2 7h20M2 12h20M2 17h12' },
  { key: 'projects', label: '项目经历', icon: 'M4 6h16v12H4z M8 6v12 M16 6v12' },
  { key: 'skills', label: '技能总结', icon: 'M9 2h6v4H9z M5 6h14v14H5z' },
];

const LOADING_STEPS = ['检索知识库中...', '审核内容中...', '撰写段落中...'];

export default function GenerateView({
  structuredJD,
  gapReport,
  onResumeGenerated,
  templateId,
}: GenerateViewProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [section, setSection] = useState<Section>('experience');
  const [result, setResult] = useState<GenerateResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loadingStep, setLoadingStep] = useState(0);
  const [exporting, setExporting] = useState(false);

  async function handleGenerate() {
    if (!structuredJD || status === 'loading') return;

    setStatus('loading');
    setErrorMsg(null);
    setLoadingStep(0);

    // 模拟步骤切换动画
    const stepTimer = setInterval(() => {
      setLoadingStep((s) => Math.min(s + 1, 2));
    }, 1500);

    try {
      const res = await generateResume(structuredJD, section, gapReport);
      setResult(res);
      setStatus('done');
      // US-8：把生成结果传给 MainLayout，供中栏 ResumePreview 实时预览
      onResumeGenerated?.(res.content);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : '生成失败');
    } finally {
      clearInterval(stepTimer);
    }
  }

  // 导出 PDF（US-7）
  async function handleExportPDF() {
    if (!result || exporting) return;

    setExporting(true);
    setErrorMsg(null);
    try {
      // 构造简历数据
      const resumeData: Record<string, unknown> = {
        name: '我的简历',
        ...result.content,
      };

      // 从 structuredJD 获取目标岗位
      const jobTitle =
        (structuredJD as Record<string, unknown>)?.job_title as string ?? '';
      const company =
        (structuredJD as Record<string, unknown>)?.company as string ?? '';

      const blob = await exportResumePDF(resumeData, jobTitle, company, templateId);

      // 触发浏览器下载
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `resume_${jobTitle || 'export'}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '导出失败');
      console.error('PDF 导出失败:', err);
    } finally {
      setExporting(false);
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

  // 加载中
  if (status === 'loading') {
    return (
      <div className="space-y-3">
        <div className="flex flex-col items-center gap-3 py-4">
          {LOADING_STEPS.map((label, i) => (
            <div
              key={label}
              className="flex items-center gap-2 text-xs"
              style={{ opacity: i <= loadingStep ? 1 : 0.4 }}
            >
              {i < loadingStep ? (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--color-success)' }}>
                  <path d="M3 8l3.5 3.5L13 4" />
                </svg>
              ) : i === loadingStep ? (
                <svg className="animate-spin w-3.5 h-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--color-brand-primary)' }}>
                  <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
                </svg>
              ) : (
                <div className="w-3.5 h-3.5 rounded-full border border-border-default" />
              )}
              <span className={i === loadingStep ? 'text-text-primary font-medium' : 'text-text-muted'}>
                {label}
              </span>
            </div>
          ))}
        </div>
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

  // 空闲 + 已生成后的选择+生成区域
  return (
    <div className="space-y-2">
      {/* 段落选择 */}
      <div className="flex gap-1">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            onClick={() => {
              setSection(s.key);
              setResult(null);
              setStatus('idle');
            }}
            className={`flex-1 text-xs px-2 py-1.5 rounded-md transition-all ${
              section === s.key
                ? 'bg-brand-primary text-white font-medium'
                : 'border border-border-default text-text-secondary hover:border-brand-primary hover:text-brand-primary'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* 生成按钮 */}
      {status === 'idle' && (
        <button
          onClick={handleGenerate}
          className="w-full text-xs px-3 py-2 rounded-md bg-brand-primary text-white font-medium cursor-pointer hover:opacity-90 transition-opacity"
        >
          生成{SECTIONS.find((s) => s.key === section)?.label}
        </button>
      )}

      {/* 生成结果 */}
      {result && status === 'done' && (
        <div className="space-y-2">
          {/* 来源标注 */}
          <div className="text-[10px] text-text-muted">
            基于 {result.sources_used} 条知识库记录生成
          </div>

          {/* 反思提示 */}
          {result.reflection.issues_found > 0 && (
            <div className="bg-[rgba(217,119,6,0.08)] border border-[rgba(217,119,6,0.2)] rounded-md p-2">
              <div className="text-xs text-warning font-medium mb-1">
                审核发现 {result.reflection.issues_found} 个问题
              </div>
              <ul className="space-y-0.5">
                {result.reflection.issues.map((issue, i) => (
                  <li key={i} className="text-[11px] text-text-secondary">
                    • {issue.type}: {issue.description}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 内容展示 */}
          <GenerateContent section={result.section} content={result.content} />

          {/* 导出错误提示 */}
          {errorMsg && (
            <div className="text-xs text-error">{errorMsg}</div>
          )}

          {/* 导出 + 重新生成按钮 */}
          <div className="flex gap-2">
            <button
              onClick={handleExportPDF}
              disabled={exporting}
              className="flex-1 text-xs px-3 py-1.5 rounded-md bg-brand-primary text-white font-medium cursor-pointer hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {exporting ? '导出中...' : '导出 PDF'}
            </button>
            <button
              onClick={handleGenerate}
              className="flex-1 text-xs px-3 py-1.5 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer hover:border-brand-primary hover:text-brand-primary transition-all"
            >
              重新生成
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** 根据段落类型渲染不同内容 */
function GenerateContent({
  section,
  content,
}: {
  section: string;
  content: Record<string, unknown>;
}) {
  if (section === 'experience') {
    const experiences = (content.experience as Array<Record<string, unknown>>) || [];
    return (
      <div className="space-y-2">
        {experiences.map((exp, i) => (
          <div key={i} className="border border-border-subtle rounded-md p-2">
            <div className="flex items-center justify-between mb-1">
              <div>
                <span className="text-sm font-medium text-text-primary">
                  {exp.role as string}
                </span>
                <span className="text-xs text-text-tertiary ml-1">
                  @ {exp.company as string}
                </span>
              </div>
              <span className="text-[10px] text-text-muted">
                {exp.period as string}
              </span>
            </div>
            <ul className="space-y-0.5">
              {((exp.highlights as string[]) || []).map((h, j) => (
                <li key={j} className="text-xs text-text-secondary flex gap-1">
                  <span className="text-brand-primary flex-shrink-0">·</span>
                  <span>{h}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    );
  }

  if (section === 'projects') {
    const projects = (content.projects as Array<Record<string, unknown>>) || [];
    return (
      <div className="space-y-2">
        {projects.map((proj, i) => (
          <div key={i} className="border border-border-subtle rounded-md p-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-text-primary">
                {proj.name as string}
              </span>
              <span className="text-[10px] text-text-muted">
                {proj.period as string}
              </span>
            </div>
            <div className="text-xs text-text-tertiary mb-1">
              {proj.role as string}
            </div>
            <div className="text-xs text-text-secondary mb-1">
              {proj.description as string}
            </div>
            {((proj.tech_stack as string[]) || []).length > 0 && (
              <div className="flex flex-wrap gap-1">
                {(proj.tech_stack as string[]).map((tech, j) => (
                  <span
                    key={j}
                    className="text-[9px] px-1.5 py-0.5 rounded bg-bg-tertiary text-text-secondary"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (section === 'skills') {
    const skills = (content.skills as Record<string, Array<Record<string, string>>>) || {};
    const categories = [
      { key: 'tech_stack', label: '技术栈' },
      { key: 'hard_skills', label: '硬技能' },
      { key: 'soft_skills', label: '软技能' },
    ];
    return (
      <div className="space-y-2">
        {categories.map((cat) => {
          const items = skills[cat.key] || [];
          if (items.length === 0) return null;
          return (
            <div key={cat.key}>
              <div className="text-xs font-medium text-text-secondary mb-1">
                {cat.label}
              </div>
              <div className="space-y-0.5">
                {items.map((item, j) => (
                  <div key={j} className="text-xs flex gap-1">
                    <span className="text-text-primary font-medium flex-shrink-0">
                      {item.name}
                    </span>
                    <span className="text-text-tertiary">
                      {item.context}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  return null;
}
