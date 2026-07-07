// frontend/src/components/diff/DiffView.tsx
// US-10：版本 Diff 对比视图
// - 顶部双节点选择器（自动触发 diff 请求）
// - 汇总统计条（added / removed / modified）
// - 三段折叠面板（experience / projects / skills）
// - 差异项渲染为结构化卡片（非原始 JSON）
// - added/removed/modified 三色高亮 + 字段标签

import { useEffect, useState } from 'react';
import { getNodeDiff } from '@/lib/api';
import type { ResumeNode } from '@/types/tree';
import type { DiffItem, DiffResult, DiffSections } from '@/types/diff';

interface DiffViewProps {
  /** 版本树节点列表，用于选择器 */
  nodes: ResumeNode[];
}

type Status = 'idle' | 'loading' | 'done' | 'error';

/** 差异类型视觉配置 */
const TYPE_CONFIG: Record<
  DiffItem['type'],
  { label: string; textCls: string; bgCls: string; borderCls: string; icon: string }
> = {
  added: {
    label: '新增',
    textCls: 'text-success',
    bgCls: 'bg-[rgba(5,150,105,0.06)]',
    borderCls: 'border-l-2 border-success',
    icon: 'M8 3v10M3 8h10',
  },
  removed: {
    label: '移除',
    textCls: 'text-error',
    bgCls: 'bg-[rgba(220,38,38,0.06)]',
    borderCls: 'border-l-2 border-error',
    icon: 'M3 8h10',
  },
  modified: {
    label: '修改',
    textCls: 'text-warning',
    bgCls: 'bg-[rgba(217,119,6,0.06)]',
    borderCls: 'border-l-2 border-warning',
    icon: 'M2 9c1.5-3 3.5-3 6 0s4.5 3 6 0',
  },
};

/** 三段元信息 */
const SECTION_META: { key: keyof DiffSections; label: string }[] = [
  { key: 'experience', label: '工作经历' },
  { key: 'projects', label: '项目经历' },
  { key: 'skills', label: '技能' },
];

// === 结构化渲染辅助 ===

/** 从差异项的 value/old_value/new_value 中提取结构化数据 */
function extractObject(item: DiffItem): Record<string, unknown> | null {
  const v = item.type === 'added' || item.type === 'removed'
    ? item.value
    : item.new_value ?? item.old_value;
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    return v as Record<string, unknown>;
  }
  return null;
}

/** 安全转字符串 */
function asStr(v: unknown): string {
  if (v === undefined || v === null) return '';
  if (typeof v === 'string') return v;
  return String(v);
}

/** 安全转字符串数组 */
function asStrArr(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(asStr);
  return [];
}

// === 经历卡片渲染 ===

function ExperienceCard({ item }: { item: DiffItem }) {
  const obj = extractObject(item);
  const cfg = TYPE_CONFIG[item.type];

  if (!obj) {
    // 非结构化数据（如 highlights 子项），简单渲染
    return <SimpleValue item={item} />;
  }

  const company = asStr(obj.company);
  const role = asStr(obj.role);
  const period = asStr(obj.period);
  const highlights = asStrArr(obj.highlights);

  return (
    <div className={`${cfg.bgCls} ${cfg.borderCls} rounded-r-md py-2 px-3 space-y-1`}>
      {/* 标题行 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg.textCls} ${cfg.bgCls} border ${cfg.borderCls} flex-shrink-0`}>
        {cfg.label}
          </span>
          <span className="text-sm font-medium text-text-primary truncate">
            {role || '未知职位'} {company && <span className="text-text-tertiary font-normal">@ {company}</span>}
          </span>
        </div>
        {period && <span className="text-[10px] text-text-muted flex-shrink-0">{period}</span>}
      </div>

      {/* highlights */}
      {highlights.length > 0 && (
        <ul className="space-y-0.5 ml-1">
          {highlights.map((h, i) => (
            <li key={i} className="text-xs text-text-secondary flex gap-1.5">
              <span className={`${cfg.textCls} flex-shrink-0`}>•</span>
              <span className={item.type === 'removed' ? 'line-through text-text-tertiary' : ''}>{h}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// === 项目卡片渲染 ===

function ProjectCard({ item }: { item: DiffItem }) {
  const obj = extractObject(item);
  const cfg = TYPE_CONFIG[item.type];

  if (!obj) {
    return <SimpleValue item={item} />;
  }

  const name = asStr(obj.name);
  const role = asStr(obj.role);
  const period = asStr(obj.period);
  const description = asStr(obj.description);
  const techStack = asStrArr(obj.tech_stack);

  return (
    <div className={`${cfg.bgCls} ${cfg.borderCls} rounded-r-md py-2 px-3 space-y-1`}>
      {/* 标题行 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg.textCls} ${cfg.bgCls} border ${cfg.borderCls} flex-shrink-0`}>
        {cfg.label}
          </span>
          <span className="text-sm font-medium text-text-primary truncate">
            {name || '未知项目'}
          </span>
          {role && <span className="text-xs text-text-tertiary">· {role}</span>}
        </div>
        {period && <span className="text-[10px] text-text-muted flex-shrink-0">{period}</span>}
      </div>

      {/* 描述 */}
      {description && (
        <div className={`text-xs text-text-secondary ml-1 ${item.type === 'removed' ? 'line-through' : ''}`}>
          {description}
        </div>
      )}

      {/* 技术栈标签 */}
      {techStack.length > 0 && (
        <div className="flex flex-wrap gap-1 ml-1">
          {techStack.map((t, i) => (
            <span
              key={i}
              className={`text-[10px] px-1.5 py-0.5 rounded ${
                item.type === 'removed'
                  ? 'bg-[rgba(220,38,38,0.08)] text-text-tertiary line-through'
                  : item.type === 'added'
                  ? 'bg-[rgba(5,150,105,0.08)] text-success'
                  : 'bg-bg-tertiary text-text-secondary'
              }`}
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// === 技能卡片渲染 ===

function SkillCard({ item }: { item: DiffItem }) {
  const obj = extractObject(item);
  const cfg = TYPE_CONFIG[item.type];

  if (!obj) {
    return <SimpleValue item={item} />;
  }

  const name = asStr(obj.name);
  const context = asStr(obj.context);
  // 从 field 提取类别: "skills.tech_stack[0]" → "tech_stack"
  const fieldParts = item.field.split('.');
  const category = fieldParts.length > 1 ? fieldParts[1]?.replace(/\[\d+\]/, '') : '';
  const categoryLabels: Record<string, string> = {
    tech_stack: '技术栈',
    hard_skills: '硬技能',
    soft_skills: '软技能',
  };
  const categoryLabel = categoryLabels[category] ?? category;

  return (
    <div className={`${cfg.bgCls} ${cfg.borderCls} rounded-r-md py-1.5 px-3`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg.textCls} ${cfg.bgCls} border ${cfg.borderCls} flex-shrink-0`}>
          {cfg.label}
        </span>
        {categoryLabel && (
          <span className="text-[10px] text-text-muted px-1 py-0.5 rounded bg-bg-tertiary flex-shrink-0">
            {categoryLabel}
          </span>
        )}
        <span className="text-sm font-medium text-text-primary">
          {name}
        </span>
        {context && (
          <span className={`text-xs ${item.type === 'removed' ? 'text-text-tertiary line-through' : 'text-text-secondary'}`}>
            — {context}
          </span>
        )}
      </div>
    </div>
  );
}

// === modified 字段级对比渲染 ===

function ModifiedFields({ item }: { item: DiffItem }) {
  const cfg = TYPE_CONFIG[item.type];
  const details = item.details ?? [];

  if (details.length === 0) {
    // 无子项差异，展示 old → new
    return (
      <div className={`${cfg.bgCls} ${cfg.borderCls} rounded-r-md py-1.5 px-3 space-y-1`}>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg.textCls} ${cfg.bgCls} border ${cfg.borderCls}`}>
            {cfg.label}
          </span>
          <span className="text-xs text-text-muted">{item.field}</span>
        </div>
        <div className="flex items-start gap-2 ml-1">
          <div className="flex-1">
            <span className="text-[10px] text-error mr-1">旧:</span>
            <span className="text-xs text-text-tertiary line-through">{asStr(item.old_value)}</span>
          </div>
          <span className="text-text-muted text-xs">→</span>
          <div className="flex-1">
            <span className="text-[10px] text-success mr-1">新:</span>
            <span className="text-xs text-text-primary">{asStr(item.new_value)}</span>
          </div>
        </div>
      </div>
    );
  }

  // 有子项差异，渲染每个字段
  return (
    <div className={`${cfg.bgCls} ${cfg.borderCls} rounded-r-md py-2 px-3 space-y-1.5`}>
      <div className="flex items-center gap-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg.textCls} ${cfg.bgCls} border ${cfg.borderCls}`}>
          {cfg.label}
        </span>
        <span className="text-xs text-text-muted">{item.field}</span>
      </div>
      {details.map((sub, i) => (
        <div key={i} className="ml-2 space-y-0.5">
          <div className="flex items-start gap-2">
            <span className="text-[10px] text-text-tertiary mt-0.5 flex-shrink-0 w-20">
              {sub.field}
            </span>
            <div className="flex-1 space-y-0.5">
              {sub.old_value !== undefined && sub.old_value !== null && (
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-error flex-shrink-0">旧</span>
                  <span className="text-xs text-text-tertiary line-through">
                    {asStr(sub.old_value) || JSON.stringify(sub.old_value)}
                  </span>
                </div>
              )}
              {sub.new_value !== undefined && sub.new_value !== null && (
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-success flex-shrink-0">新</span>
                  <span className="text-xs text-text-primary">
                    {asStr(sub.new_value) || JSON.stringify(sub.new_value)}
                  </span>
                </div>
              )}
              {sub.type === 'added' && sub.value !== undefined && (
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-success flex-shrink-0">+</span>
                  <span className="text-xs text-success">{asStr(sub.value)}</span>
                </div>
              )}
              {sub.type === 'removed' && sub.value !== undefined && (
                <div className="flex items-center gap-1">
                  <span className="text-[9px] text-error flex-shrink-0">-</span>
                  <span className="text-xs text-text-tertiary line-through">{asStr(sub.value)}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// === 简单值渲染（用于非结构化数据） ===

function SimpleValue({ item }: { item: DiffItem }) {
  const cfg = TYPE_CONFIG[item.type];
  const v = item.value ?? item.new_value ?? item.old_value;
  const isStr = typeof v === 'string';
  const text = isStr ? v : JSON.stringify(v, null, 2);

  return (
    <div className={`${cfg.bgCls} ${cfg.borderCls} rounded-r-md py-1.5 px-3`}>
      <div className="flex items-center gap-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${cfg.textCls} ${cfg.bgCls} border ${cfg.borderCls} flex-shrink-0`}>
          {cfg.label}
        </span>
        <span className={`text-xs ${item.type === 'removed' ? 'text-text-tertiary line-through' : 'text-text-secondary'}`}>
          {text}
        </span>
      </div>
    </div>
  );
}

/** 根据段落类型选择对应卡片渲染器 */
function DiffItemCard({ item, sectionKey }: { item: DiffItem; sectionKey: keyof DiffSections }) {
  if (item.type === 'modified') {
    return <ModifiedFields item={item} />;
  }
  if (sectionKey === 'experience') return <ExperienceCard item={item} />;
  if (sectionKey === 'projects') return <ProjectCard item={item} />;
  if (sectionKey === 'skills') return <SkillCard item={item} />;
  return <SimpleValue item={item} />;
}

// === 主组件 ===

export default function DiffView({ nodes }: DiffViewProps) {
  const [nodeAId, setNodeAId] = useState<string>('');
  const [nodeBId, setNodeBId] = useState<string>('');
  const [status, setStatus] = useState<Status>('idle');
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    experience: true,
    projects: false,
    skills: false,
  });
  const [copiedSection, setCopiedSection] = useState<string | null>(null);

  useEffect(() => {
    if (!nodeAId || !nodeBId) {
      setStatus('idle');
      setDiffResult(null);
      setErrorMsg(null);
      return;
    }
    if (nodeAId === nodeBId) {
      setStatus('idle');
      setDiffResult(null);
      setErrorMsg(null);
      return;
    }

    let cancelled = false;
    setStatus('loading');
    setErrorMsg(null);
    getNodeDiff(nodeAId, nodeBId)
      .then((result) => {
        if (cancelled) return;
        setDiffResult(result);
        setStatus('done');
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus('error');
        setErrorMsg(err instanceof Error ? err.message : '获取差异失败');
      });

    return () => {
      cancelled = true;
    };
  }, [nodeAId, nodeBId]);

  function toggleSection(key: string) {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  async function handleCopySection(sectionKey: keyof DiffSections) {
    const sectionData = diffResult?.diffs[sectionKey] ?? [];
    try {
      await navigator.clipboard.writeText(JSON.stringify(sectionData, null, 2));
      setCopiedSection(sectionKey);
      window.setTimeout(() => {
        setCopiedSection((cur) => (cur === sectionKey ? null : cur));
      }, 1500);
    } catch {
      // 静默失败
    }
  }

  const bothSelected = Boolean(nodeAId) && Boolean(nodeBId);
  const sameNode = nodeAId === nodeBId && bothSelected;
  const hasAnyDiff =
    diffResult !== null &&
    (diffResult.summary.added +
      diffResult.summary.removed +
      diffResult.summary.modified >
      0);

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      {/* 1. 顶部节点选择器 */}
      <div className="bg-bg-secondary border border-border-default rounded-lg p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 4h6M6 2v6M10 12h4M12 8v8" />
          </svg>
          版本对比
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-[11px] text-text-tertiary font-medium">节点 1</label>
            <select
              value={nodeAId}
              onChange={(e) => setNodeAId(e.target.value)}
              className="w-full text-sm px-2.5 py-1.5 rounded-md border border-border-default bg-bg-primary text-text-primary cursor-pointer focus:outline-none focus:border-brand-primary transition-colors"
            >
              <option value="">请选择节点</option>
              {nodes.map((n) => (
                <option key={n.node_id} value={n.node_id}>
                  {n.title} ({n.node_id})
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[11px] text-text-tertiary font-medium">节点 2</label>
            <select
              value={nodeBId}
              onChange={(e) => setNodeBId(e.target.value)}
              className="w-full text-sm px-2.5 py-1.5 rounded-md border border-border-default bg-bg-primary text-text-primary cursor-pointer focus:outline-none focus:border-brand-primary transition-colors"
            >
              <option value="">请选择节点</option>
              {nodes.map((n) => (
                <option key={n.node_id} value={n.node_id}>
                  {n.title} ({n.node_id})
                </option>
              ))}
            </select>
          </div>
        </div>
        {/* 方向说明 */}
        {bothSelected && !sameNode && (
          <div className="text-[10px] text-text-muted">
            以节点 2 为基准，查看节点 1 相对它的变化
          </div>
        )}
      </div>

      {/* 2. 内容区 */}
      {!bothSelected ? (
        <div className="flex flex-col items-center justify-center py-16 text-text-muted text-sm gap-2">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 3H5a2 2 0 0 0-2 2v4M15 3h4a2 2 0 0 1 2 2v4M9 21H5a2 2 0 0 1-2-2v-4M15 21h4a2 2 0 0 0 2-2v-4" />
          </svg>
          请选择两个节点进行对比
        </div>
      ) : sameNode ? (
        <div className="flex flex-col items-center justify-center py-16 text-warning text-sm gap-2">
          请选择不同的节点
        </div>
      ) : status === 'loading' ? (
        <div className="flex flex-col items-center gap-2 py-16">
          <svg className="animate-spin w-5 h-5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--color-brand-primary)' }}>
            <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
          </svg>
          <span className="text-xs text-text-secondary">正在对比节点差异...</span>
        </div>
      ) : status === 'error' ? (
        <div className="flex flex-col items-center gap-2 py-16 text-error text-sm">
          <span>{errorMsg ?? '获取差异失败'}</span>
          <span className="text-xs text-text-muted">请检查后端服务或重新选择节点</span>
        </div>
      ) : diffResult && !hasAnyDiff ? (
        <div className="flex flex-col items-center justify-center py-16 text-success text-sm gap-2">
          两节点内容完全一致
        </div>
      ) : diffResult ? (
        <div className="space-y-4">
          {/* 节点标题对比 */}
          <div className="flex items-center justify-center gap-3 text-xs text-text-tertiary">
            <span className="px-2 py-1 rounded-md bg-bg-tertiary text-text-primary font-medium">
              节点 1：{diffResult.node_a.title}
            </span>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 8h6M9 5l3 3-3 3" />
            </svg>
            <span className="px-2 py-1 rounded-md bg-bg-tertiary text-text-primary font-medium">
              节点 2：{diffResult.node_b.title}
            </span>
          </div>

          {/* 汇总统计条 */}
          <div className="flex items-center gap-4 bg-bg-secondary border border-border-default rounded-lg px-4 py-2.5">
            {[
              { key: 'added', label: '新增', count: diffResult.summary.added, dotCls: 'bg-success', textCls: 'text-success' },
              { key: 'removed', label: '移除', count: diffResult.summary.removed, dotCls: 'bg-error', textCls: 'text-error' },
              { key: 'modified', label: '修改', count: diffResult.summary.modified, dotCls: 'bg-warning', textCls: 'text-warning' },
            ].map((s) => (
              <div key={s.key} className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${s.dotCls}`} />
                <span className="text-xs text-text-secondary">{s.label}</span>
                <span className={`text-sm font-mono font-semibold ${s.textCls}`}>{s.count}</span>
              </div>
            ))}
          </div>

          {/* 三段折叠面板 */}
          <div className="space-y-2">
            {SECTION_META.map(({ key, label }) => {
              const items = diffResult.diffs[key] ?? [];
              const isOpen = expanded[key];
              return (
                <div key={key} className="bg-bg-secondary border border-border-default rounded-lg overflow-hidden">
                  {/* 段标题 */}
                  <div className="flex items-center px-3 py-2.5 border-b border-border-subtle">
                    <button
                      onClick={() => toggleSection(key)}
                      className="flex items-center gap-2 text-sm font-medium text-text-primary cursor-pointer bg-transparent border-none p-0"
                    >
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 16 16"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className={`transition-transform ${isOpen ? 'rotate-90' : ''}`}
                      >
                        <path d="M6 4l4 4-4 4" />
                      </svg>
                      {label}
                      <span className="text-xs px-1.5 py-px rounded-full bg-bg-tertiary text-text-tertiary font-mono">
                        {items.length}
                      </span>
                    </button>
                    <button
                      onClick={() => handleCopySection(key)}
                      disabled={items.length === 0}
                      className="ml-auto inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-border-default text-text-secondary bg-bg-primary cursor-pointer hover:border-brand-primary hover:text-brand-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {copiedSection === key ? '已复制' : '复制差异'}
                    </button>
                  </div>

                  {/* 段内容 */}
                  {isOpen && (
                    <div className="p-3 space-y-2">
                      {items.length === 0 ? (
                        <div className="text-xs text-text-muted py-3 text-center">
                          该段无差异
                        </div>
                      ) : (
                        items.map((item, idx) => (
                          <DiffItemCard key={`${item.field}-${idx}`} item={item} sectionKey={key} />
                        ))
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
