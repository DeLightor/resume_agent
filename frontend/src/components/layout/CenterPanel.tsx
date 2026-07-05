// frontend/src/components/layout/CenterPanel.tsx
// 中栏：面包屑 + Tab Pills（版本树/预览/Diff）+ VersionTree 画布
// US-2：联动节点选中、详情浮层、新建节点弹窗、面包屑动态路径

import { useCallback, useState } from 'react';
import Breadcrumb from '@/components/common/Breadcrumb';
import VersionTree from '@/components/tree/VersionTree';
import NodeDetailPanel from '@/components/tree/NodeDetailPanel';
import CreateNodeModal from '@/components/tree/CreateNodeModal';
import type { ResumeNode, TreeData } from '@/types/tree';

const TAB_PILLS = ['版本树', '编辑器', 'Diff 对比'] as const;

interface CenterPanelProps {
  /** 版本树刷新 key，变化时重新拉取 */
  treeRefreshKey?: number;
  /** 触发版本树刷新（新建节点后调用，递增 treeRefreshKey） */
  onTreeRefresh?: () => void;
}

/**
 * 从选中节点回溯 parent_id 链生成路径。
 * 未选中或无树数据时返回 ['master']。
 */
function computePath(tree: TreeData | null, node: ResumeNode | null): string[] {
  if (!tree || !node) return ['master'];
  const path: string[] = [];
  let current: ResumeNode | null = node;
  while (current) {
    const cur: ResumeNode = current;
    path.unshift(cur.node_type === 'master' ? cur.node_id : (cur.title || cur.node_id));
    const parent = tree.nodes.find((n) => n.node_id === cur.parent_id);
    current = parent ?? null;
  }
  if (path.length === 0 || path[0] !== 'master') path.unshift('master');
  return path;
}

export default function CenterPanel({
  treeRefreshKey,
  onTreeRefresh,
}: CenterPanelProps) {
  const [activeTab, setActiveTab] = useState<string>('版本树');
  const [selectedNode, setSelectedNode] = useState<ResumeNode | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  // 树数据由 VersionTree onTreeLoad 回灌，用于路径回溯与新建节点父选项
  const [tree, setTree] = useState<TreeData | null>(null);

  const handleNodeSelect = useCallback((node: ResumeNode) => {
    setSelectedNode(node);
  }, []);

  const handleTreeLoad = useCallback((data: TreeData) => {
    setTree(data);
  }, []);

  const handleCreated = useCallback(() => {
    setShowCreateModal(false);
    onTreeRefresh?.();
  }, [onTreeRefresh]);

  const breadcrumbPath = computePath(tree, selectedNode);

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
      {/* Breadcrumb + Tab pills */}
      <div className="flex items-center px-5 py-3 gap-2 border-b border-border-subtle text-sm">
        <Breadcrumb path={breadcrumbPath} />
        <div className="ml-auto flex gap-0.5 bg-bg-tertiary rounded-md p-0.5">
          {TAB_PILLS.map((pill) => (
            <button
              key={pill}
              onClick={() => setActiveTab(pill)}
              className={`px-4 py-1 rounded-sm text-xs transition-all border-none cursor-pointer font-body ${
                activeTab === pill
                  ? 'bg-bg-elevated text-text-primary font-medium shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              {pill}
            </button>
          ))}
        </div>
      </div>

      {/* Version tree canvas */}
      <div className="flex-1 relative overflow-hidden">
        <VersionTree
          refreshKey={treeRefreshKey}
          onNodeSelect={handleNodeSelect}
          onTreeLoad={handleTreeLoad}
        />
        <NodeDetailPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
        />
      </div>

      {/* Canvas toolbar */}
      <div className="flex items-center gap-3 px-5 py-3 border-t border-border-subtle border-b border-border-subtle">
        <button
          onClick={() => setShowCreateModal(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-transparent text-text-secondary text-sm font-medium border border-border-default rounded-md cursor-pointer transition-all font-body hover:border-border-strong hover:text-text-primary hover:bg-bg-hover"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M8 3v10M3 8h10" />
          </svg>
          新建分支
        </button>
        <button
          className="inline-flex items-center gap-2 px-5 py-2 text-white text-sm font-medium border-none rounded-md cursor-pointer font-body transition-all hover:brightness-110 hover:-translate-y-px"
          style={{
            background:
              'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
            boxShadow: 'var(--shadow-glow-primary)',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1.5l1.7 3.5 3.8.6-2.8 2.7.7 3.8L8 10.1 4.6 12.1l.7-3.8L2.5 5.6l3.8-.6z" />
          </svg>
          为该岗位动态生成
        </button>
        <button className="inline-flex items-center gap-2 px-5 py-2 bg-transparent text-text-secondary text-sm font-medium border border-border-default rounded-md cursor-pointer transition-all font-body hover:border-border-strong hover:text-text-primary hover:bg-bg-hover">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M2 4h12M2 8h8M2 12h10" />
          </svg>
          版本对比 Diff
        </button>
        <div className="ml-auto flex gap-0.5 bg-bg-tertiary rounded-md p-0.5">
          {['经典学术', '大厂技术', '极简风'].map((tpl) => (
            <button
              key={tpl}
              className={`px-4 py-1 rounded-sm text-xs transition-all border-none cursor-pointer font-body ${
                tpl === '大厂技术'
                  ? 'bg-brand-primary text-white font-medium'
                  : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              {tpl}
            </button>
          ))}
        </div>
      </div>

      {/* 新建节点弹窗 */}
      <CreateNodeModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleCreated}
        parentOptions={tree?.nodes ?? []}
      />
    </main>
  );
}
