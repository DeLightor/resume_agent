// frontend/src/components/jd/JDCard.tsx
// JD 结构化结果展示卡片（US-4）
// - 顶部：公司 / 岗位名称（可编辑）
// - 技术栈（紫色标签，var(--color-node-branch)）
// - 硬技能（橙色标签，var(--color-node-company)）
// - 软技能（青色标签，var(--color-node-master)）
// - 加分项（列表）
// 每项均支持就地编辑（contenteditable），编辑结果保存在组件本地 state。

import { useEffect, useRef, useState } from 'react';
import type { JDAnalysisResult, JDStructured } from '@/types/jd';

interface JDCardProps {
  result: JDAnalysisResult;
  /** 将用户最后编辑的 JD 同步给工作台上下文和投递快照。 */
  onStructuredChange?: (structured: JDStructured) => void;
}

/** 标签配色方案 */
interface ColorScheme {
  color: string;
  bg: string;
  border: string;
}

/** 技术栈 — 紫色系 */
const TECH_SCHEME: ColorScheme = {
  color: 'var(--color-node-branch)',
  bg: 'rgba(124, 58, 237, 0.08)',
  border: 'rgba(124, 58, 237, 0.22)',
};
/** 硬技能 — 橙色系 */
const HARD_SCHEME: ColorScheme = {
  color: 'var(--color-node-company)',
  bg: 'rgba(217, 119, 6, 0.08)',
  border: 'rgba(217, 119, 6, 0.22)',
};
/** 软技能 — 青色系 */
const SOFT_SCHEME: ColorScheme = {
  color: 'var(--color-node-master)',
  bg: 'rgba(8, 145, 178, 0.08)',
  border: 'rgba(8, 145, 178, 0.22)',
};

/** 可编辑列表字段名 */
type EditableListKey = 'tech_stack' | 'hard_skills' | 'soft_skills' | 'bonus_items';

/**
 * 可编辑标签（contenteditable span）。
 * 通过 ref + useEffect 同步外部 value，仅在不一致时更新 DOM，避免光标跳动。
 */
function EditableTag({
  value,
  scheme,
  onChange,
}: {
  value: string;
  scheme: ColorScheme;
  onChange: (v: string) => void;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el && el.textContent !== value) {
      el.textContent = value;
    }
  }, [value]);

  return (
    <span
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      spellCheck={false}
      onBlur={(e) => {
        const text = e.currentTarget.textContent?.trim() ?? '';
        if (text !== value) onChange(text);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.currentTarget.blur();
        }
      }}
      className="text-xs px-2.5 py-1 rounded-full border font-mono tracking-wider cursor-text outline-none transition-all inline-block hover:brightness-105 focus:bg-bg-hover"
      style={{
        color: scheme.color,
        backgroundColor: scheme.bg,
        borderColor: scheme.border,
      }}
    />
  );
}

/**
 * 可编辑文本（contenteditable span），用于岗位名 / 公司名 / 列表项。
 */
function EditableText({
  value,
  className,
  onChange,
}: {
  value: string;
  className?: string;
  onChange: (v: string) => void;
}) {
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el && el.textContent !== value) {
      el.textContent = value;
    }
  }, [value]);

  return (
    <span
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      spellCheck={false}
      onBlur={(e) => {
        const text = e.currentTarget.textContent?.trim() ?? '';
        if (text !== value) onChange(text);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.currentTarget.blur();
        }
      }}
      className={`cursor-text outline-none inline-block min-w-[24px] rounded-sm focus:bg-bg-hover ${
        className ?? ''
      }`}
    />
  );
}

/** 标签分区（技术栈 / 硬技能 / 软技能） */
function TagSection({
  title,
  items,
  scheme,
  onEdit,
}: {
  title: string;
  items: string[];
  scheme: ColorScheme;
  onEdit: (index: number, value: string) => void;
}) {
  return (
    <>
      <div className="text-xs font-semibold text-text-tertiary uppercase tracking-wide mb-2 mt-3">
        {title}
      </div>
      {items.length === 0 ? (
        <div className="text-xs text-text-muted">（暂无）</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item, i) => (
            <EditableTag
              key={`${title}-${i}`}
              value={item}
              scheme={scheme}
              onChange={(v) => onEdit(i, v)}
            />
          ))}
        </div>
      )}
    </>
  );
}

/** 加分项列表分区 */
function BonusSection({
  items,
  onEdit,
}: {
  items: string[];
  onEdit: (index: number, value: string) => void;
}) {
  return (
    <>
      <div className="text-xs font-semibold text-text-tertiary uppercase tracking-wide mb-2 mt-3">
        加分项
      </div>
      {items.length === 0 ? (
        <div className="text-xs text-text-muted">（暂无）</div>
      ) : (
        items.map((item, i) => (
          <div
            key={`bonus-${i}`}
            className="flex items-start gap-2 text-sm text-text-secondary mb-1.5 leading-snug"
          >
            <svg
              className="w-3.5 h-3.5 flex-shrink-0 mt-px text-warning"
              viewBox="0 0 16 16"
              fill="currentColor"
            >
              <path d="M8 1.5l1.7 3.5 3.8.6-2.8 2.7.7 3.8L8 10.1 4.6 12.1l.7-3.8L2.5 5.6l3.8-.6z" />
            </svg>
            <EditableText
              value={item}
              onChange={(v) => onEdit(i, v)}
              className="flex-1 text-text-secondary"
            />
          </div>
        ))
      )}
    </>
  );
}

export default function JDCard({ result, onStructuredChange }: JDCardProps) {
  const [structured, setStructured] = useState<JDStructured>(result.structured);

  useEffect(() => { onStructuredChange?.(structured); }, [structured, onStructuredChange]);

  /** 更新标量字段（job_title / company） */
  function updateField<K extends keyof JDStructured>(
    key: K,
    value: JDStructured[K],
  ) {
    setStructured((prev) => ({ ...prev, [key]: value }));
  }

  /** 更新列表字段某一项 */
  function updateList(key: EditableListKey, index: number, value: string) {
    setStructured((prev) => {
      const arr = [...prev[key]];
      arr[index] = value;
      return { ...prev, [key]: arr };
    });
  }

  return (
    <div className="bg-bg-tertiary rounded-lg p-4 border border-border-subtle">
      {/* 公司 / 岗位名称 */}
      <div className="text-md font-semibold mb-3 text-text-primary">
        <EditableText
          value={structured.company}
          onChange={(v) => updateField('company', v)}
          className="text-text-primary"
        />
        <span className="text-text-tertiary font-normal"> / </span>
        <EditableText
          value={structured.job_title}
          onChange={(v) => updateField('job_title', v)}
          className="text-text-tertiary font-normal"
        />
      </div>

      <TagSection
        title="技术栈"
        items={structured.tech_stack}
        scheme={TECH_SCHEME}
        onEdit={(i, v) => updateList('tech_stack', i, v)}
      />
      <TagSection
        title="硬技能"
        items={structured.hard_skills}
        scheme={HARD_SCHEME}
        onEdit={(i, v) => updateList('hard_skills', i, v)}
      />
      <TagSection
        title="软技能"
        items={structured.soft_skills}
        scheme={SOFT_SCHEME}
        onEdit={(i, v) => updateList('soft_skills', i, v)}
      />
      <BonusSection
        items={structured.bonus_items}
        onEdit={(i, v) => updateList('bonus_items', i, v)}
      />
    </div>
  );
}
