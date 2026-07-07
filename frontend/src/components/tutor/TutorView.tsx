// frontend/src/components/tutor/TutorView.tsx
// US-11: AI 导师学习建议
// - 基于 Gap 报告的 missing/partial 技能生成学习路径
// - 学习路径三步（概念→实践→验证）
// - 资源列表（文档/课程/项目/面试题），可点击跳转
// - 学习状态标记（已掌握/学习中/待开始），localStorage 持久化

import { useState } from 'react';
import { getTutorSuggestions } from '@/lib/api';
import type { GapItem } from '@/types/gap';
import type { TutorSuggestion, TutorResource, LearnStatus } from '@/types/tutor';

interface TutorViewProps {
  /** Gap 报告中的技能项列表 */
  gapItems: GapItem[];
}

type Status = 'idle' | 'loading' | 'done' | 'error';

const RESOURCE_ICONS: Record<string, string> = {
  document: 'M4 2h8l4 4v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z M12 2v4h4',
  course: 'M2 4h12v8H2z M5 14h6 M8 11v3',
  project: 'M3 3h10v10H3z M6 6h4v4H6z',
  interview: 'M2 3h12v6H2z M5 11h6 M8 9v2 M4 13h8',
};

const RESOURCE_LABELS: Record<string, string> = {
  document: '文档',
  course: '课程',
  project: '项目',
  interview: '面试题',
};

const STATUS_CONFIG: Record<LearnStatus, { label: string; cls: string }> = {
  mastered: { label: '已掌握', cls: 'text-success bg-[rgba(5,150,105,0.08)]' },
  learning: { label: '学习中', cls: 'text-warning bg-[rgba(217,119,6,0.08)]' },
  pending: { label: '待开始', cls: 'text-text-tertiary bg-bg-tertiary' },
};

const STATUS_KEY_PREFIX = 'tutor-status-';

function getStatusFromStorage(skill: string): LearnStatus {
  try {
    const v = localStorage.getItem(`${STATUS_KEY_PREFIX}${skill}`);
    if (v === 'mastered' || v === 'learning' || v === 'pending') return v;
  } catch {
    // localStorage 不可用时静默
  }
  return 'pending';
}

function setStatusInStorage(skill: string, status: LearnStatus) {
  try {
    localStorage.setItem(`${STATUS_KEY_PREFIX}${skill}`, status);
  } catch {
    // 静默
  }
}

export default function TutorView({ gapItems }: TutorViewProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [suggestions, setSuggestions] = useState<TutorSuggestion[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMap, setStatusMap] = useState<Record<string, LearnStatus>>({});

  // 过滤出 missing / partial 的技能
  const targetItems = gapItems.filter(
    (item) => item.status === 'missing' || item.status === 'partial',
  );

  async function handleGenerate() {
    if (targetItems.length === 0 || status === 'loading') return;
    setStatus('loading');
    setErrorMsg(null);
    try {
      const result = await getTutorSuggestions(
        targetItems.map((item) => ({
          skill: item.skill,
          category: item.category,
          status: item.status,
        })),
      );
      setSuggestions(result.suggestions);
      // 初始化状态 map
      const map: Record<string, LearnStatus> = {};
      for (const s of result.suggestions) {
        map[s.skill] = getStatusFromStorage(s.skill);
      }
      setStatusMap(map);
      setStatus('done');
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : '获取学习建议失败');
    }
  }

  function handleStatusChange(skill: string, newStatus: LearnStatus) {
    setStatusMap((prev) => ({ ...prev, [skill]: newStatus }));
    setStatusInStorage(skill, newStatus);
  }

  // 无缺口技能
  if (targetItems.length === 0) {
    return null;
  }

  // 空闲状态
  if (status === 'idle') {
    return (
      <button
        onClick={handleGenerate}
        className="w-full text-xs px-3 py-2 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer hover:border-brand-primary hover:text-brand-primary transition-all flex items-center justify-center gap-1.5"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
          <path d="M8 5v3l2 2" />
        </svg>
        获取 AI 导师学习建议
      </button>
    );
  }

  // 加载中
  if (status === 'loading') {
    return (
      <div className="flex flex-col items-center gap-2 py-4">
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
        <span className="text-xs text-text-secondary">正在生成学习建议...</span>
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

  // 已生成建议
  return (
    <div className="space-y-2.5">
      {/* 链接免责声明 */}
      <div className="text-[10px] text-text-muted leading-tight">
        资源链接由 AI 生成，可能失效，仅供参考。
      </div>

      {suggestions.map((suggestion) => {
        const learnStatus = statusMap[suggestion.skill] ?? 'pending';
        const statusCfg = STATUS_CONFIG[learnStatus];
        return (
          <div
            key={suggestion.skill}
            className="border border-border-subtle rounded-md p-2.5 space-y-2"
          >
            {/* 技能名 + 状态选择器 */}
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-text-primary truncate">
                {suggestion.skill}
              </span>
              <select
                value={learnStatus}
                onChange={(e) =>
                  handleStatusChange(suggestion.skill, e.target.value as LearnStatus)
                }
                className={`text-[10px] px-2 py-0.5 rounded-full font-medium border-none cursor-pointer ${statusCfg.cls}`}
              >
                <option value="pending">待开始</option>
                <option value="learning">学习中</option>
                <option value="mastered">已掌握</option>
              </select>
            </div>

            {/* 学习路径三步 */}
            <div className="space-y-1">
              {[
                { label: '概念', value: suggestion.learning_path.concept, color: 'text-brand-primary' },
                { label: '实践', value: suggestion.learning_path.practice, color: 'text-warning' },
                { label: '验证', value: suggestion.learning_path.validation, color: 'text-success' },
              ].map((step) => (
                <div key={step.label} className="flex items-start gap-1.5">
                  <span className={`text-[10px] font-medium flex-shrink-0 mt-0.5 ${step.color}`}>
                    {step.label}
                  </span>
                  <span className="text-xs text-text-secondary leading-tight">
                    {step.value}
                  </span>
                </div>
              ))}
            </div>

            {/* 资源列表 */}
            {suggestion.resources.length > 0 && (
              <div className="space-y-1 pt-1 border-t border-border-subtle">
                {suggestion.resources.map((resource: TutorResource, idx: number) => (
                  <a
                    key={idx}
                    href={resource.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-start gap-1.5 text-xs text-text-secondary hover:text-brand-primary transition-colors group"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 16 16"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="flex-shrink-0 mt-0.5 opacity-60 group-hover:opacity-100"
                    >
                      <path d={RESOURCE_ICONS[resource.type] || RESOURCE_ICONS.document} />
                    </svg>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1">
                        <span className="text-[9px] text-text-muted bg-bg-tertiary px-1 py-0.5 rounded flex-shrink-0">
                          {RESOURCE_LABELS[resource.type] || resource.type}
                        </span>
                        <span className="text-text-primary group-hover:text-brand-primary truncate">
                          {resource.title}
                        </span>
                      </div>
                      {resource.description && (
                        <div className="text-[10px] text-text-muted leading-tight mt-0.5">
                          {resource.description}
                        </div>
                      )}
                    </div>
                  </a>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {/* 重新生成 */}
      <button
        onClick={handleGenerate}
        className="w-full text-xs px-3 py-1.5 rounded-md border border-border-default text-text-secondary bg-bg-elevated cursor-pointer hover:border-brand-primary hover:text-brand-primary transition-all"
      >
        重新生成建议
      </button>
    </div>
  );
}
