// frontend/src/data/mockTree.ts
// Mock 版本树数据，参考 design.md 第 5.3 节

import type { TreeData } from '@/types/tree';

export const mockTree: TreeData = {
  nodes: [
    {
      version: 0,
      id: 'master',
      node_id: 'master',
      parent_id: null,
      node_type: 'master',
      title: 'Master 主干',
      company: null,
      direction: null,
    },
    {
      version: 0,
      id: 'branch-security',
      node_id: 'security',
      parent_id: 'master',
      node_type: 'branch',
      title: '安全岗方向',
      company: null,
      direction: '安全',
    },
    {
      version: 0,
      id: 'branch-algorithm',
      node_id: 'algorithm',
      parent_id: 'master',
      node_type: 'branch',
      title: '算法岗方向',
      company: null,
      direction: '算法',
    },
    {
      version: 0,
      id: 'company-tencent-rs',
      node_id: 'tencent-researcher',
      parent_id: 'security',
      node_type: 'company',
      title: 'Tencent 安全研究员',
      company: 'Tencent',
    },
    {
      version: 0,
      id: 'company-bytedance-sec',
      node_id: 'bytedance-security',
      parent_id: 'security',
      node_type: 'company',
      title: 'ByteDance 安全工程师',
      company: 'ByteDance',
    },
    {
      version: 0,
      id: 'company-bytedance-algo',
      node_id: 'bytedance-algorithm',
      parent_id: 'algorithm',
      node_type: 'company',
      title: 'ByteDance 算法工程师',
      company: 'ByteDance',
    },
  ],
  edges: [
    { source: 'master', target: 'security' },
    { source: 'master', target: 'algorithm' },
    { source: 'security', target: 'tencent-researcher' },
    { source: 'security', target: 'bytedance-security' },
    { source: 'algorithm', target: 'bytedance-algorithm' },
  ],
};
