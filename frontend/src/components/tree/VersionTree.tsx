// frontend/src/components/tree/VersionTree.tsx
// React Flow 画布，从 GET /api/tree 获取版本树并渲染

import { useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { getTree } from '@/lib/api';
import type { TreeData, ResumeNode } from '@/types/tree';
import MasterNode, { type MasterNodeData } from './nodes/MasterNode';
import BranchNode, { type BranchNodeData } from './nodes/BranchNode';
import CompanyNode, { type CompanyNodeData } from './nodes/CompanyNode';

const nodeTypes = {
  master: MasterNode,
  branch: BranchNode,
  company: CompanyNode,
};

/** 列布局 x 坐标：master → branch → company（右移避开 React Flow 控件） */
const X_MASTER = 180;
const X_BRANCH = 440;
const X_COMPANY = 740;

/** 各层垂直间距 */
const BRANCH_GAP = 180;
const COMPANY_GAP = 110;

interface VersionTreeProps {
  /** 变化时触发重新拉取版本树（由上传成功后递增） */
  refreshKey?: number;
  /** 节点被选中时回调（传递对应的 ResumeNode） */
  onNodeSelect?: (node: ResumeNode) => void;
  /** 版本树加载完成时回调（供父层回溯路径 / 父选项） */
  onTreeLoad?: (tree: TreeData) => void;
}

/** 根据节点类型映射为 ReactFlow Node data */
function toFlowNode(n: ResumeNode, position: { x: number; y: number }): Node {
  const base = {
    id: n.node_id,
    type: n.node_type,
    position,
    draggable: true,
    selectable: true,
    connectable: false,
  };

  if (n.node_type === 'master') {
    return {
      ...base,
      data: { label: 'master', sublabel: 'main' } as MasterNodeData,
    };
  }
  if (n.node_type === 'branch') {
    return {
      ...base,
      data: { label: n.title, direction: n.direction ?? '', has_upstream_update: n.has_upstream_update ?? false } as BranchNodeData,
    };
  }
  // company: title 形如 "Tencent 安全研究员"
  const [company, ...rest] = n.title.split(' ');
  return {
    ...base,
    data: {
      label: n.title,
      company: company,
      role: rest.join(' '),
      has_upstream_update: n.has_upstream_update ?? false,
    } as CompanyNodeData,
  };
}

/** 计算三层布局位置（master 居中，branch / company 各自垂直居中分布） */
function layoutTree(tree: TreeData): { nodes: Node[]; edges: Edge[] } {
  const masters = tree.nodes.filter((n) => n.node_type === 'master');
  const branches = tree.nodes.filter((n) => n.node_type === 'branch');
  const companies = tree.nodes.filter((n) => n.node_type === 'company');

  const nodes: Node[] = [];

  // master：取第一个，垂直居中于 0
  masters.forEach((n, i) => {
    nodes.push(toFlowNode(n, { x: X_MASTER, y: i * BRANCH_GAP }));
  });

  // branch：垂直居中分布
  const branchOffset = (branches.length - 1) * (BRANCH_GAP / 2);
  branches.forEach((n, i) => {
    nodes.push(toFlowNode(n, { x: X_BRANCH, y: i * BRANCH_GAP - branchOffset }));
  });

  // company：垂直居中分布
  const companyOffset = (companies.length - 1) * (COMPANY_GAP / 2);
  companies.forEach((n, i) => {
    nodes.push(toFlowNode(n, { x: X_COMPANY, y: i * COMPANY_GAP - companyOffset }));
  });

  const edges: Edge[] = tree.edges.map((e, i) => ({
    id: `e-${i}`,
    source: e.source,
    target: e.target,
    type: 'smoothstep',
    animated: false,
    style: { stroke: '#a78bfa', strokeWidth: 1.8, opacity: 0.5 },
  }));

  return { nodes, edges };
}

export default function VersionTree({
  refreshKey = 0,
  onNodeSelect,
  onTreeLoad,
}: VersionTreeProps) {
  const [tree, setTree] = useState<TreeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTree()
      .then((data) => {
        if (!cancelled) {
          setTree(data);
          setLoading(false);
          onTreeLoad?.(data);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载版本树失败');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, onTreeLoad]);

  // 当 tree 数据变化时，重新计算布局并更新 nodes/edges
  useEffect(() => {
    if (!tree) return;
    const { nodes: flowNodes, edges: flowEdges } = layoutTree(tree);
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [tree, setNodes, setEdges]);

  // 加载中
  if (loading) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-sm text-text-muted">加载版本树...</div>
      </div>
    );
  }

  // 加载失败
  if (error) {
    return (
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
        <div className="text-sm text-error">✗ 加载失败</div>
        <div className="text-xs text-text-muted">{error}</div>
      </div>
    );
  }

  // 空树
  if (!tree || tree.nodes.length === 0) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="text-sm text-text-muted">
          暂无版本树节点，拖入旧简历即可创建初始版本
        </div>
      </div>
    );
  }

  return (
    <div className="absolute inset-0">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_event, flowNode) => {
          if (!onNodeSelect || !tree) return;
          const resumeNode = tree.nodes.find((n) => n.node_id === flowNode.id);
          if (resumeNode) onNodeSelect(resumeNode);
        }}
        nodeTypes={nodeTypes}
        nodesDraggable
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e2e8f0" gap={30} size={1} />
        <Controls
          position="bottom-right"
          style={{
            backgroundColor: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '6px',
          }}
          showInteractive={false}
        />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-3 left-4 flex gap-5 text-xs text-text-tertiary bg-bg-secondary border border-border-subtle rounded-md px-4 py-2 z-10">
        <div className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: 'var(--color-node-master)', boxShadow: '0 0 6px var(--color-node-master)' }}
          />
          <span>主干节点</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: 'var(--color-node-branch)', boxShadow: '0 0 6px var(--color-node-branch)' }}
          />
          <span>方向分支</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: 'var(--color-node-company)', boxShadow: '0 0 6px var(--color-node-company)' }}
          />
          <span>公司节点</span>
        </div>
      </div>
    </div>
  );
}
