// frontend/src/components/tree/NodeDetailPanel.tsx
// 节点详情浮层：中栏画布右上角，显示选中节点的类型/标题/方向或公司/内容预览

import type { NodeType, ResumeNode } from '@/types/tree';

interface NodeDetailPanelProps {
  node: ResumeNode | null;
  onClose: () => void;
}

const TYPE_LABEL: Record<NodeType, string> = {
  master: '主干节点',
  branch: '方向分支',
  company: '公司节点',
};

/** 类型文字色（master 青 / branch 紫 / company 橙） */
const TYPE_TEXT_CLASS: Record<NodeType, string> = {
  master: 'text-node-master',
  branch: 'text-node-branch',
  company: 'text-node-company',
};

/** 类型圆点背景色 */
const TYPE_DOT_CLASS: Record<NodeType, string> = {
  master: 'bg-node-master',
  branch: 'bg-node-branch',
  company: 'bg-node-company',
};

/** content_json 预览最多展示的行数 */
const PREVIEW_MAX_LINES = 8;

export default function NodeDetailPanel({ node, onClose }: NodeDetailPanelProps) {
  if (!node) return null;

  const type = node.node_type;
  const content = node.content_json;

  const contentPreview = content
    ? JSON.stringify(content, null, 2)
        .split('\n')
        .slice(0, PREVIEW_MAX_LINES)
        .join('\n')
    : null;

  return (
    <div className="absolute right-4 top-4 z-20 w-[280px] bg-bg-secondary rounded-lg shadow-lg border border-border-subtle p-4">
      {/* 顶部：类型标签 + 关闭按钮 */}
      <div className="flex items-start justify-between mb-3">
        <span
          className={`inline-flex items-center gap-1.5 text-xs font-medium ${TYPE_TEXT_CLASS[type]}`}
        >
          <span className={`w-2 h-2 rounded-full ${TYPE_DOT_CLASS[type]}`} />
          {TYPE_LABEL[type]}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="text-text-muted hover:text-text-primary transition-colors cursor-pointer border-none bg-transparent p-0 leading-none text-lg"
        >
          ×
        </button>
      </div>

      {/* 标题 */}
      <div className="text-sm font-semibold text-text-primary mb-2 break-words">
        {node.title}
      </div>

      {/* 方向 / 公司 */}
      {type === 'branch' && node.direction && (
        <div className="text-xs text-text-secondary mb-1">
          方向：<span className="text-text-primary">{node.direction}</span>
        </div>
      )}
      {type === 'company' && node.company && (
        <div className="text-xs text-text-secondary mb-1">
          公司：<span className="text-text-primary">{node.company}</span>
        </div>
      )}
      {type === 'company' && (
        <div className="text-xs text-text-secondary mb-1">
          岗位：
          <span className="text-text-primary">
            {node.title.replace(`${node.company ?? ''}`, '').trim() || '—'}
          </span>
        </div>
      )}

      {/* content_json 预览 */}
      <div className="mt-3 pt-3 border-t border-border-subtle">
        <div className="text-xs text-text-tertiary mb-1.5">内容预览</div>
        {contentPreview ? (
          <pre className="text-[10px] font-mono text-text-secondary bg-bg-tertiary rounded-md p-2 overflow-auto max-h-40 whitespace-pre-wrap break-all m-0">
            {contentPreview}
          </pre>
        ) : (
          <div className="text-xs text-text-muted">暂无内容</div>
        )}
      </div>
    </div>
  );
}
