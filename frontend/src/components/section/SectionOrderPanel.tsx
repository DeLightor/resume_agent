// frontend/src/components/section/SectionOrderPanel.tsx
// US-13: 简历段落排序面板
// - 拖拽排序（HTML5 Drag API，不引入新依赖）
// - 显示/隐藏开关
// - 共享节点草稿队列 800ms
// - 节点切换时重新加载

import { useState, useRef } from 'react';
import { useNodeDraftById } from '@/hooks/useNodeDraft';
import type { SectionItem } from '@/types/section';

interface SectionOrderPanelProps {
  nodeId: string | null;
  /** section_order 保存后通知外部更新 selectedNode 的 content_json */
  onOrderUpdated?: (sections: SectionItem[]) => void;
}

const defaultSections: SectionItem[] = [
  { key: 'summary', title: '自我评价', visible: true },
  { key: 'experience', title: '工作经历', visible: true },
  { key: 'projects', title: '项目经历', visible: true },
  { key: 'skills', title: '技能总结', visible: true },
  { key: 'education', title: '教育背景', visible: true },
  { key: 'awards', title: '获奖经历', visible: false },
  { key: 'publications', title: '论文/专利', visible: false },
  { key: 'certificates', title: '证书', visible: false },
];
function sectionItems(value: unknown): SectionItem[] {
  const sections: SectionItem[] = [];
  if (Array.isArray(value)) {
    for (const item of value) {
      const base = defaultSections.find(section => section.key === item?.key);
      if (base && !sections.some(section => section.key === base.key)) {
        sections.push({ ...base, title: typeof item.title === 'string' ? item.title : base.title, visible: item.visible !== false });
      }
    }
  }
  for (const item of defaultSections) if (!sections.some(section => section.key === item.key)) sections.push({ ...item });
  return sections;
}

export default function SectionOrderPanel({ nodeId, onOrderUpdated }: SectionOrderPanelProps) {
  const draft = useNodeDraftById(nodeId);
  const { status: saveStatus, loading } = draft;
  const sections = sectionItems(draft.content?.section_order);
  const [collapsed, setCollapsed] = useState(false);
  const dragIndex = useRef<number | null>(null);
  function triggerSave(newSections: SectionItem[]) {
    draft.edit(content => { content.section_order = newSections; });
    onOrderUpdated?.(newSections);
  }

  // 拖拽排序
  function handleDragStart(idx: number) {
    dragIndex.current = idx;
  }

  function handleDragOver(e: React.DragEvent, idx: number) {
    e.preventDefault();
    if (dragIndex.current === null || dragIndex.current === idx) return;
    const newSections = [...sections];
    const dragged = newSections[dragIndex.current];
    newSections.splice(dragIndex.current, 1);
    newSections.splice(idx, 0, dragged);
    dragIndex.current = idx;
    triggerSave(newSections);
  }

  function handleDragEnd() {
    dragIndex.current = null;
  }

  // 切换显示/隐藏
  function toggleVisible(idx: number) {
    const newSections = sections.map((s, i) =>
      i === idx ? { ...s, visible: !s.visible } : s,
    );
    triggerSave(newSections);
  }

  if (!nodeId) {
    return null;
  }

  const statusText = {
    idle: '',
    pending: '待保存…',
    conflict: '版本冲突',
    saving: '保存中...',
    saved: '已保存',
    error: '保存失败',
  }[saveStatus];

  return (
    <div className="border-b border-border-subtle">
      {/* 标题栏 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-bg-tertiary transition-colors"
      >
        <div className="flex items-center gap-1.5">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-brand-primary"
          >
            <path d="M2 4h12M2 8h12M2 12h12" />
            <circle cx="6" cy="4" r="0.5" fill="currentColor" />
            <circle cx="10" cy="8" r="0.5" fill="currentColor" />
            <circle cx="4" cy="12" r="0.5" fill="currentColor" />
          </svg>
          <span className="text-xs font-semibold text-text-primary">段落排序</span>
          {statusText && (
            <span
              className={`text-[10px] ${saveStatus === 'error' ? 'text-error' : 'text-text-muted'}`}
            >
              {statusText}
            </span>
          )}
        </div>
        <svg
          width="10"
          height="10"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`text-text-muted transition-transform ${collapsed ? '' : 'rotate-90'}`}
        >
          <path d="M6 4l4 4-4 4" />
        </svg>
      </button>

      {(draft.error || draft.loadError) && <div role="alert" className="px-3 py-2 text-xs text-error">
        {draft.error || draft.loadError}
        {draft.loadError ? <button onClick={() => void draft.retryLoad()} className="ml-2 underline">重试加载</button>
          : saveStatus === 'conflict' ? <button onClick={() => { if (window.confirm('重新加载将丢弃本地未保存草稿，是否继续？')) void draft.reload(); }} className="ml-2 underline">重新加载服务端版本</button>
          : <button onClick={() => void draft.flush()} className="ml-2 underline">重试保存</button>}
      </div>}
      {!collapsed && (
        <div className="px-3 pb-3 space-y-1">
          {loading ? (
            <div className="flex items-center justify-center py-2">
              <svg
                className="animate-spin w-3 h-3 text-text-tertiary"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
              </svg>
            </div>
          ) : (
            (draft.content ? sections : []).map((section, idx) => (
              <div
                key={section.key}
                draggable
                onDragStart={() => handleDragStart(idx)}
                onDragOver={(e) => handleDragOver(e, idx)}
                onDragEnd={handleDragEnd}
                className={`flex items-center gap-2 px-2 py-1.5 rounded border border-border-subtle bg-bg-elevated cursor-move transition-all ${
                  dragIndex.current === idx ? 'opacity-50 border-brand-primary' : ''
                } ${!section.visible ? 'opacity-60' : ''}`}
              >
                {/* 拖拽手柄 */}
                <svg
                  width="10"
                  height="14"
                  viewBox="0 0 10 14"
                  fill="currentColor"
                  className="text-text-muted flex-shrink-0"
                >
                  <circle cx="2" cy="3" r="1" />
                  <circle cx="8" cy="3" r="1" />
                  <circle cx="2" cy="7" r="1" />
                  <circle cx="8" cy="7" r="1" />
                  <circle cx="2" cy="11" r="1" />
                  <circle cx="8" cy="11" r="1" />
                </svg>

                {/* 段落标题 */}
                <span className="text-xs text-text-primary flex-1">
                  {section.title}
                </span>

                {/* 序号 */}
                <span className="text-[10px] text-text-muted w-4 text-center">
                  {idx + 1}
                </span>

                {/* 显示/隐藏开关 */}
                <button
                  onClick={() => toggleVisible(idx)}
                  className={`relative w-7 h-3.5 rounded-full transition-colors ${
                    section.visible ? 'bg-brand-primary' : 'bg-border-default'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 w-2.5 h-2.5 rounded-full bg-white transition-transform ${
                      section.visible ? 'translate-x-3.5' : 'translate-x-0.5'
                    }`}
                  />
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
