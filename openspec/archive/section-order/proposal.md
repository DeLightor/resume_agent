# US-13: 简历段落可排序

## 概述

在编辑器 Tab 新增"段落排序"面板，用户可拖拽调整简历段落的顺序，并控制每个段落的显示/隐藏。段落顺序存入节点 `content_json.section_order`，子节点创建时继承。

## 段落清单（8 段）

| key | 默认标题 |
|-----|---------|
| summary | 自我评价 |
| experience | 工作经历 |
| projects | 项目经历 |
| skills | 技能总结 |
| education | 教育背景 |
| awards | 获奖经历 |
| publications | 论文/专利 |
| certificates | 证书 |

## 提议变更

### 后端

**1. 段落排序 API**（`api/section_order.py`）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/tree/node/{node_id}/section-order` | GET | 获取段落顺序 |
| `/api/tree/node/{node_id}/section-order` | PUT | 更新段落顺序 |

`section_order` 数据结构：
```json
[
  { "key": "summary", "title": "自我评价", "visible": true },
  { "key": "experience", "title": "工作经历", "visible": true },
  { "key": "projects", "title": "项目经历", "visible": true },
  { "key": "skills", "title": "技能总结", "visible": true },
  { "key": "education", "title": "教育背景", "visible": true },
  { "key": "awards", "title": "获奖经历", "visible": false },
  { "key": "publications", "title": "论文/专利", "visible": false },
  { "key": "certificates", "title": "证书", "visible": false }
]
```

**2. 节点继承**

在 `tree.py` 的 `create_node` 中，创建子节点时从父节点继承 `section_order`（与 personal_info 同理）。

**3. 默认顺序**

节点没有 `section_order` 时返回默认 8 段顺序。

### 前端

**1. SectionOrderPanel 组件**（`components/section/SectionOrderPanel.tsx`）

- 位置：编辑器 Tab 中栏工具栏下方
- 每个段落一行：拖拽手柄 + 标题 + 显示/隐藏开关
- 拖拽用原生 HTML5 Drag API（不引入新依赖）
- 拖拽后实时更新顺序，防抖保存 500ms
- 显示/隐藏切换即时保存

**2. ResumePreview 联动**

`ResumePreview` 按 `section_order` 渲染段落，`visible=false` 的段落不渲染。

### 数据存储

`section_order` 存储在 `resume_versions.content_json.section_order`：
```json
{
  "section_order": [...],
  "personal_info": {...},
  "experience": [...],
  ...
}
```

## 约束

- 不引入 dnd-kit 等拖拽库，用原生 HTML5 Drag API
- `section_order` 作为 content_json 的新字段，不影响现有字段
- 子节点继承是创建时的快照拷贝
- PDF 导出按排序后的段落顺序渲染（后续 US 实现）
