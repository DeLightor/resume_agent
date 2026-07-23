# US-17: 上游变更检测与提示

## 概述

master 节点修改 personal_info 后，所有子节点自动检测差异并标记"有更新可合并"。版本树画布显示橙色徽标，侧栏显示变更提示。

## 变更类型

- **数据库 schema 变更**（High Risk）：resume_versions 表新增 2 列
- **后端 API**：新增 3 个端点 + 修改 personal_info 更新逻辑
- **前端**：版本树节点徽标 + 侧栏提示

## 数据库变更

### schema.sql 新增

```sql
ALTER TABLE resume_versions ADD COLUMN has_upstream_update INTEGER DEFAULT 0;
ALTER TABLE resume_versions ADD COLUMN upstream_changes TEXT;
```

- `has_upstream_update`: 0/1 标记是否有上游变更
- `upstream_changes`: JSON 字符串，记录变更详情

### 迁移策略

- schema.sql 使用 `IF NOT EXISTS`（幂等建表）
- 启动时执行 `ALTER TABLE ADD COLUMN`（幂等，列已存在时忽略错误）
- 现有数据默认 `has_upstream_update=0`，无破坏性影响

## 后端 API

### 1. 变更检测触发

在 `PUT /tree/node/{node_id}/personal-info` 中，保存后调用 `_propagate_upstream_changes(node_id)`

### 2. 变更传播逻辑

```python
def _propagate_upstream_changes(node_id: str):
    """master 修改 personal_info 后，递归标记所有子节点。"""
    # 1. 获取修改节点的 personal_info
    # 2. 递归查找所有子节点（parent_id = node_id）
    # 3. 对比 personal_info 字段级差异
    # 4. 有差异 → 标记 has_upstream_update=1, upstream_changes=JSON
```

### 3. 新增端点

- `GET /api/tree/node/{node_id}/upstream-changes` — 获取上游变更列表
- `POST /api/tree/node/{node_id}/merge` — 合并指定字段（US-18 用）
- `POST /api/tree/node/{node_id}/merge/all` — 批量全部接受（US-18 用）

## 前端

- 版本树节点：有 `has_upstream_update` 时显示橙色圆点徽标
- 节点侧栏：显示"上游有 N 项变更可合并"提示条
- 树数据结构：`getTree` 返回的 nodes 新增 `has_upstream_update` 字段

## 约束

- 仅检测 personal_info 字段（contact/education/summary）
- 不自动传播到内容段落（experience/projects 等）
- 递归遍历限 ≤ 50 节点
- 变更传播在 personal_info 更新时同步触发（不异步）
