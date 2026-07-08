// frontend/src/components/tree/nodes/BranchNode.tsx
// 圆角矩形节点，紫色（bg-node-branch），参考 design.md 第 7.3 节

import { Handle, Position, type NodeProps } from '@xyflow/react';

export interface BranchNodeData {
  label: string;
  direction?: string;
  has_upstream_update?: boolean;
  [key: string]: unknown;
}

export default function BranchNode({ data, selected }: NodeProps) {
  const nodeData = data as unknown as BranchNodeData;
  return (
    <div
      className={`flex items-center justify-center rounded-lg bg-bg-secondary text-node-branch border-2 px-6 py-3 min-w-[100px] shadow-glow-secondary cursor-grab active:cursor-grabbing transition-shadow relative ${
        selected ? 'border-brand-primary shadow-glow-primary' : 'border-node-branch'
      }`}
    >
      <span className="text-sm font-semibold pointer-events-none">
        {nodeData.label}
      </span>
      {nodeData.has_upstream_update && (
        <span
          className="absolute -top-1 -right-1 w-3 h-3 bg-orange-500 rounded-full border-2 border-white shadow-sm"
          title="有上游变更待合并"
        />
      )}
      <Handle type="source" position={Position.Right} className="!bg-node-branch !border-node-branch !w-2 !h-2" />
      <Handle type="target" position={Position.Left} className="!bg-node-branch !border-node-branch !w-2 !h-2" />
    </div>
  );
}
