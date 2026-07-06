// frontend/src/components/generate/GenerateView.tsx
// AI 简历生成（US-6）+ 智能补全（US-9）
// 检索 → 反思 → 撰写 3 步工作流
// 修复：切换段落不清空已有结果 + 支持单项选择加入预览

import { useEffect, useState, useCallback } from 'react';
import { exportResumePDF, generateResume, generateSuggestions } from '@/lib/api';
import type {
  GeneratedExperience,
  GeneratedProject,
  GeneratedSkill,
  GeneratedSkills,
  GenerateResult,
} from '@/types/generate';
import type { Suggestion } from '@/types/suggest';
import SuggestionCards from './SuggestionCards';

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

/** 合并所有段落的结果用于预览，排除被用户取消选择的条目 */
function mergeAllSections(
  resultsBySection: Record<string, GenerateResult | null>,
  excludedBySection: Record<string, Set<number>>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = {};
  for (const sec of ['experience', 'projects', 'skills']) {
    const res = resultsBySection[sec];
    if (!res?.content) continue;
    const excluded = excludedBySection[sec] ?? new Set<number>();
    if (sec === 'experience') {
      const all = (res.content.experience as GeneratedExperience[]) ?? [];
      merged.experience = all.filter((_, i) => !excluded.has(i));
    } else if (sec === 'projects') {
      const all = (res.content.projects as GeneratedProject[]) ?? [];
      merged.projects = all.filter((_, i) => !excluded.has(i));
    } else if (sec === 'skills') {
      merged.skills = res.content.skills;
    }
    // 拷贝其他可能的字段
    for (const [k, v] of Object.entries(res.content)) {
      if (k !== 'experience' && k !== 'projects' && k !== 'skills') {
        merged[k] = v;
      }
    }
  }
  return merged;
}

export default function GenerateView({
  structuredJD,
  gapReport,
  onResumeGenerated,
  templateId,
}: GenerateViewProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [section, setSection] = useState<Section>('experience');
  // 按段落缓存结果，切换时不丢失
  const [resultsBySection, setResultsBySection] = useState<
    Record<string, GenerateResult | null>
  >({});
  // 按段落缓存建议
  const [suggestionsBySection, setSuggestionsBySection] = useState<
    Record<string, Suggestion[]>
  >({});
  // 按段落记录已排除的条目索引
  const [excludedBySection, setExcludedBySection] = useState<
    Record<string, Set<number>>
  >({});
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loadingStep, setLoadingStep] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestLoadedBySection, setSuggestLoadedBySection] = useState<
    Record<string, boolean>
  >({});

  // 当前段落的结果（从缓存派生）
  const result = resultsBySection[section] ?? null;
  const suggestions = suggestionsBySection[section] ?? [];
  const suggestLoaded = suggestLoadedBySection[section] ?? false;

  /** 通知 MainLayout 更新预览（合并所有段落） */
  const notifyPreview = useCallback(
    (
      newResults: Record<string, GenerateResult | null>,
      newExcluded: Record<string, Set<number>>,
    ) => {
      const merged = mergeAllSections(newResults, newExcluded);
      onResumeGenerated?.(merged);
    },
    [onResumeGenerated],
  );

  async function handleGenerate() {
    if (!structuredJD || status === 'loading') return;

    setStatus('loading');
    setErrorMsg(null);
    setLoadingStep(0);

    const stepTimer = setInterval(() => {
      setLoadingStep((s) => Math.min(s + 1, 2));
    }, 1500);

    try {
      const res = await generateResume(structuredJD, section, gapReport);
      const newResults = { ...resultsBySection, [section]: res };
      setResultsBySection(newResults);
      // 重置排除状态
      const newExcluded = { ...excludedBySection, [section]: new Set<number>() };
      setExcludedBySection(newExcluded);
      // 重置建议状态
      setSuggestionsBySection((prev) => ({ ...prev, [section]: [] }));
      setSuggestLoadedBySection((prev) => ({ ...prev, [section]: false }));
      setStatus('done');
      // 通知预览
      notifyPreview(newResults, newExcluded);
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : '生成失败');
    } finally {
      clearInterval(stepTimer);
    }
  }

  /** 切换段落：从缓存恢复，不清空 */
  function handleSectionChange(newSection: Section) {
    setSection(newSection);
    const cached = resultsBySection[newSection];
    if (cached) {
      setStatus('done');
    } else {
      setStatus('idle');
    }
  }

  /** 切换单个条目的选择状态 */
  function toggleItemExclusion(idx: number) {
    const current = new Set(excludedBySection[section] ?? []);
    if (current.has(idx)) {
      current.delete(idx);
    } else {
      current.add(idx);
    }
    const newExcluded = { ...excludedBySection, [section]: current };
    setExcludedBySection(newExcluded);
    notifyPreview(resultsBySection, newExcluded);
  }

  // US-9：生成成功后自动获取补全建议
  useEffect(() => {
    if (status === 'done' && result && structuredJD && !suggesting && !suggestLoaded) {
      void handleSuggest();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, result, suggestLoaded]);

  async function handleSuggest() {
    if (!result || !structuredJD || suggesting) return;
    setSuggesting(true);
    try {
      const res = await generateSuggestions(
        structuredJD,
        section,
        result.content,
        gapReport,
      );
      setSuggestionsBySection((prev) => ({ ...prev, [section]: res.suggestions }));
    } catch {
      // 静默失败
    } finally {
      setSuggesting(false);
      setSuggestLoadedBySection((prev) => ({ ...prev, [section]: true }));
    }
  }

  /** US-9：采纳建议，追加内容到对应字段 */
  function handleAcceptSuggestion(suggestion: Suggestion) {
    if (!result) return;
    const text = suggestion.suggested_text;
    const content = JSON.parse(JSON.stringify(result.content)) as Record<string, unknown>;

    const arrayMatch = suggestion.field.match(/^(\w+)\[(\d+)\]/);
    const idx = arrayMatch ? parseInt(arrayMatch[2], 10) : 0;

    if (suggestion.type === 'add_highlight') {
      const exps = (content.experience as GeneratedExperience[] | undefined) ?? [];
      if (exps[idx]) {
        exps[idx] = { ...exps[idx], highlights: [...exps[idx].highlights, text] };
      }
      content.experience = exps;
    } else if (suggestion.type === 'add_detail') {
      const projs = (content.projects as GeneratedProject[] | undefined) ?? [];
      if (projs[idx]) {
        const desc = projs[idx].description;
        projs[idx] = { ...projs[idx], description: desc ? `${desc} ${text}` : text };
      }
      content.projects = projs;
    } else if (suggestion.type === 'add_tech_stack') {
      const projs = (content.projects as GeneratedProject[] | undefined) ?? [];
      if (projs[idx]) {
        projs[idx] = { ...projs[idx], tech_stack: [...projs[idx].tech_stack, text] };
      }
      content.projects = projs;
    } else if (suggestion.type === 'add_skill_context') {
      const skillMatch = suggestion.field.match(/^skills\.(\w+)\[(\d+)\]/);
      const category = skillMatch ? skillMatch[1] : 'tech_stack';
      const sIdx = skillMatch ? parseInt(skillMatch[2], 10) : 0;
      const skills = (content.skills as GeneratedSkills | undefined) ?? {
        tech_stack: [],
        hard_skills: [],
        soft_skills: [],
      };
      const list = (skills[category as keyof GeneratedSkills] as GeneratedSkill[]) ?? [];
      if (list[sIdx]) {
        list[sIdx] = {
          ...list[sIdx],
          context: list[sIdx].context ? `${list[sIdx].context} ${text}` : text,
        };
      }
      (skills as unknown as Record<string, unknown>)[category] = list;
      content.skills = skills;
    }

    const updatedResult = { ...result, content };
    const newResults = { ...resultsBySection, [section]: updatedResult };
    setResultsBySection(newResults);
    notifyPreview(newResults, excludedBySection);
    setSuggestionsBySection((prev) => ({
      ...prev,
      [section]: (prev[section] ?? []).filter((s) => s !== suggestion),
    }));
  }

  /** US-7：导出 PDF（使用所有段落的合并结果） */
  async function handleExportPDF() {
    if (exporting) return;
    const merged = mergeAllSections(resultsBySection, excludedBySection);
    if (Object.keys(merged).length === 0) return;

    setExporting(true);
    setErrorMsg(null);
    try {
      const resumeData: Record<string, unknown> = { name: '我的简历', ...merged };
      const jobTitle =
        (structuredJD as Record<string, unknown>)?.job_title as string ?? '';
      const company =
        (structuredJD as Record<string, unknown>)?.company as string ?? '';
      const blob = await exportResumePDF(resumeData, jobTitle, company, templateId);
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

  // 空闲 + 已生成后的区域
  return (
    <div className="space-y-2">
      {/* 段落选择 */}
      <div className="flex gap-1">
        {SECTIONS.map((s) => {
          const hasResult = !!resultsBySection[s.key];
          return (
            <button
              key={s.key}
              onClick={() => handleSectionChange(s.key)}
              className={`flex-1 text-xs px-2 py-1.5 rounded-md transition-all relative ${
                section === s.key
                  ? 'bg-brand-primary text-white font-medium'
                  : 'border border-border-default text-text-secondary hover:border-brand-primary hover:text-brand-primary'
              }`}
            >
              {s.label}
              {hasResult && section !== s.key && (
                <span className="absolute top-0.5 right-1 w-1.5 h-1.5 rounded-full bg-success" />
              )}
            </button>
          );
        })}
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

          {/* 内容展示（含单项选择开关） */}
          <GenerateContent
            section={result.section}
            content={result.content}
            excluded={excludedBySection[section] ?? new Set<number>()}
            onToggleExclude={toggleItemExclusion}
          />

          {/* 导出错误提示 */}
          {errorMsg && <div className="text-xs text-error">{errorMsg}</div>}

          {/* 智能补全建议（US-9） */}
          {suggesting ? (
            <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
              <svg
                className="animate-spin w-3 h-3"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                style={{ color: 'var(--color-brand-primary)' }}
              >
                <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
              </svg>
              <span>正在获取补全建议...</span>
            </div>
          ) : (
            <SuggestionCards
              suggestions={suggestions}
              onAccept={handleAcceptSuggestion}
              onDismiss={(idx) =>
                setSuggestionsBySection((prev) => ({
                  ...prev,
                  [section]: (prev[section] ?? []).filter((_, i) => i !== idx),
                }))
              }
            />
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

/** 根据段落类型渲染不同内容，含单项选择开关 */
function GenerateContent({
  section,
  content,
  excluded,
  onToggleExclude,
}: {
  section: string;
  content: Record<string, unknown>;
  excluded: Set<number>;
  onToggleExclude: (idx: number) => void;
}) {
  if (section === 'experience') {
    const experiences = (content.experience as Array<Record<string, unknown>>) || [];
    return (
      <div className="space-y-2">
        {experiences.map((exp, i) => {
          const isIncluded = !excluded.has(i);
          return (
            <div
              key={i}
              className={`border rounded-md p-2 transition-all ${
                isIncluded
                  ? 'border-brand-primary/30'
                  : 'border-border-subtle opacity-50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  {/* 选择开关 */}
                  <button
                    onClick={() => onToggleExclude(i)}
                    className="flex-shrink-0"
                    title={isIncluded ? '从预览中移除' : '加入预览'}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className={isIncluded ? 'text-brand-primary' : 'text-text-muted'}
                    >
                      {isIncluded ? (
                        <>
                          <rect x="2" y="2" width="12" height="12" rx="2" fill="currentColor" />
                          <path d="M4 8l2.5 2.5L12 5" stroke="white" strokeWidth="2" />
                        </>
                      ) : (
                        <rect x="2" y="2" width="12" height="12" rx="2" />
                      )}
                    </svg>
                  </button>
                  <div>
                    <span className="text-sm font-medium text-text-primary">
                      {exp.role as string}
                    </span>
                    <span className="text-xs text-text-tertiary ml-1">
                      @ {exp.company as string}
                    </span>
                  </div>
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
          );
        })}
      </div>
    );
  }

  if (section === 'projects') {
    const projects = (content.projects as Array<Record<string, unknown>>) || [];
    return (
      <div className="space-y-2">
        {projects.map((proj, i) => {
          const isIncluded = !excluded.has(i);
          return (
            <div
              key={i}
              className={`border rounded-md p-2 transition-all ${
                isIncluded
                  ? 'border-brand-primary/30'
                  : 'border-border-subtle opacity-50'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  {/* 选择开关 */}
                  <button
                    onClick={() => onToggleExclude(i)}
                    className="flex-shrink-0"
                    title={isIncluded ? '从预览中移除' : '加入预览'}
                  >
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className={isIncluded ? 'text-brand-primary' : 'text-text-muted'}
                    >
                      {isIncluded ? (
                        <>
                          <rect x="2" y="2" width="12" height="12" rx="2" fill="currentColor" />
                          <path d="M4 8l2.5 2.5L12 5" stroke="white" strokeWidth="2" />
                        </>
                      ) : (
                        <rect x="2" y="2" width="12" height="12" rx="2" />
                      )}
                    </svg>
                  </button>
                  <span className="text-sm font-medium text-text-primary">
                    {proj.name as string}
                  </span>
                </div>
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
          );
        })}
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
                    <span className="text-text-tertiary">{item.context}</span>
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
