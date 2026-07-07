# US-10: 版本 Diff 对比

## 概述

在版本树中选中任意两个节点，逐字段对比 content_json 差异，高亮显示新增（绿）/删除（红）/修改（黄），支持 experience / projects / skills 三大段落。

## 动机

求职者投递多家公司时，每个版本的简历突出点不同。用户需要快速看到"腾讯那版 vs 字节那版"到底改了什么——哪些经历被新增、哪些项目被移除、哪些技能描述被修改。没有 Diff 对比，用户只能手动打开两个节点逐一查看，效率低下。

## 提议变更

### 后端：新增 Diff 端点

`POST /api/tree/diff`

请求体：
```json
{
  "node_a_id": "tencent-algo",
  "node_b_id": "bytedance-algo"
}
```

响应体：
```json
{
  "ok": true,
  "data": {
    "node_a": { "node_id": "tencent-algo", "title": "腾讯-推荐算法" },
    "node_b": { "node_id": "bytedance-algo", "title": "字节-推荐算法" },
    "diffs": {
      "experience": [
        {
          "type": "added",
          "field": "experience[0]",
          "value": { "company": "字节跳动", "role": "算法工程师", ... }
        },
        {
          "type": "modified",
          "field": "experience[1].highlights[0]",
          "old_value": "主导推荐召回模型升级",
          "new_value": "主导推荐召回模型升级，离线 AUC 提升 3%"
        }
      ],
      "projects": [...],
      "skills": [...]
    },
    "summary": { "added": 3, "removed": 1, "modified": 2 }
  }
}
```

### Diff 逻辑

1. 从数据库读取两个节点的 content_json
2. 按 experience / projects / skills 三段分别对比
3. 对比策略：
   - experience: 按 company+role 匹配，找不到 → added/removed；找到 → 逐字段对比 highlights
   - projects: 按 name 匹配，找不到 → added/removed；找到 → 逐字段对比 description/tech_stack
   - skills: 按 category+name 匹配，找不到 → added/removed；找到 → 对比 context
4. 返回结构化 diff 列表 + 汇总统计

### 前端：Diff 视图组件

- CenterPanel 的 "Diff 对比" Tab 从占位改为实际渲染
- 顶部：两个节点选择器（下拉框，选项来自版本树节点列表）
- 中部：三段折叠面板（experience / projects / skills），每段展开显示差异列表
- 差异项颜色：新增绿色背景 / 删除红色背景 / 修改黄色背景
- 差异内容可复制到剪贴板

## 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/tree/diff` | POST | 两节点 content_json Diff 对比 |

## 约束

- 只对比 content_json 中的 experience / projects / skills 三段
- content_json 为 null 的节点视为空对象
- 两节点为同一节点时返回空 diff
- 不依赖外部 diff 库，自实现字段级对比
- 前端 Diff 视图复用现有版本树节点列表

## 风险

- 大量字段对比可能返回很长的 diff 列表 → 按段落折叠，默认展开第一段
- content_json 结构可能不一致（缺少某段）→ 缺失段视为空列表，不报错
