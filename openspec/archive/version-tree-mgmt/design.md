# Design: version-tree-mgmt

## 1. 后端 API 变更

### 1.1 POST /api/tree/node（改造为真实写 DB）
```python
@router.post("/node")
def create_node(req: CreateNodeRequest) -> dict:
    """新建节点，写入 resume_versions 表。
    
    验证：
    - parent_id 必须存在
    - node_type 为 branch 时 parent 必须是 master
    - node_type 为 company 时 parent 必须是 branch
    - 同一 branch 下不允许重复 company（company + parent_id 唯一）
    """
    # 生成 node_id: branch 用 direction slugify, company 用 company-role slugify
    # INSERT 到 resume_versions
    # 返回新节点
```

### 1.2 GET /api/tree/{node_id}
返回单个节点详情，包括 content_json 解析后的对象。

### 1.3 PUT /api/tree/node/{node_id}
更新节点 title / content_json。

## 2. 前端改动

### 2.1 VersionTree 增加选中回调
- 添加 `onNodeSelect?: (node: ResumeNode) => void` prop
- ReactFlow `onNodeClick` → 找到对应的 ResumeNode → 调用 onNodeSelect
- 选中节点高亮（已有 selected 样式）

### 2.2 NodeDetailPanel 组件（新）
- 位置：中栏画布右侧浮层（absolute right-4 top-4，width 280px）
- 显示：节点类型标签、标题、方向/公司名、content_json 预览（JSON 折叠）、关闭按钮
- 如果节点无 content_json，显示「暂无内容，上传简历后将自动填充」

### 2.3 Breadcrumb 动态化
- 接受 `path: string[]` prop（替代当前的 segments）
- 路径计算：选中节点 → 从 tree 数据回溯 parent_id 链 → 生成路径数组
- 未选中时显示 ['master']

### 2.4 CreateNodeModal 组件（新）
- 触发：画布工具栏「新建分支」按钮 + 节点右键菜单
- 表单：
  - 新建分支：选择 parent（默认 master）、输入方向名称
  - 新建公司：选择 parent branch、输入公司名、输入岗位
- 提交 → POST /api/tree/node → 刷新树

### 2.5 CenterPanel 联动
- 持有 `selectedNode` state
- VersionTree onNodeSelect → setSelectedNode
- Breadcrumb 接收 selectedNode 的路径
- NodeDetailPanel 接收 selectedNode
