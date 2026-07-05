# Tasks: version-tree-mgmt

## 后端
- [x] 改造 POST /api/tree/node：验证 parent 存在、写 DB、返回新节点
- [x] 新增 GET /api/tree/{node_id}：返回节点详情
- [x] 新增 PUT /api/tree/node/{node_id}：更新 title/content_json
- [x] 测试：create branch、create company、重复 company 拒绝、parent 不存在拒绝
- [x] 测试：get node、update node

## 前端
- [x] VersionTree：添加 onNodeClick 回调，选中节点高亮
- [x] NodeDetailPanel：新建组件，显示选中节点详情
- [x] Breadcrumb：接受动态 path prop，从选中节点回溯路径
- [x] CreateNodeModal：新建分支/公司节点的表单弹窗
- [x] CenterPanel：联动 selectedNode state + 面包屑路径 + 详情面板
- [x] api.ts：新增 createNode, getNode, updateNode

## 验证
- [x] 后端 pytest + ruff
- [x] 前端 typecheck + build
