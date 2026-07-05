# Change: version-tree-mgmt

## 变更类型
新增

## 变更范围
实现 US-2 版本树管理：点击节点选中+显示详情、动态面包屑路径、手动新建分支/公司节点。

## 验收标准（对齐 PRD US-2）
1. React Flow 渲染可缩放、可拖拽的树状画布 — 已完成
2. 三种节点形态区分 — 已完成
3. 点击节点 → 选中高亮 + 显示节点详情面板（JSON 内容/标题/类型）
4. 面包屑动态显示当前选中节点的路径（master → direction → company）
5. 支持手动新建分支节点（挂在 master 下）和公司节点（挂在 branch 下）
6. 节点数量 ≤ 50 时画布渲染 ≤ 100ms

## 涉及组件
- **后端**：POST /api/tree/node 改为真正写 DB；新增 GET /api/tree/{node_id} 和 PUT /api/tree/node/{node_id}
- **前端**：VersionTree 增加节点选中回调；NodeDetailPanel 组件；Breadcrumb 动态化；CreateNodeModal 组件

## 回滚方案
还原 tree.py 为桩实现，还原前端 VersionTree/CenterPanel/Breadcrumb 为当前版本。
