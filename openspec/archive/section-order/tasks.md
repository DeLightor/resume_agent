# US-13: 简历段落可排序 - 任务清单

## 后端

- [x] 创建 `backend/src/resume_agent/api/section_order.py`
  - [x] 定义默认 8 段顺序常量 `DEFAULT_SECTION_ORDER`
  - [x] `GET /tree/node/{node_id}/section-order` 端点
  - [x] `PUT /tree/node/{node_id}/section-order` 端点
- [x] 修改 `api/tree.py` 的 `create_node`
  - [x] 创建子节点时从父节点继承 `section_order`
- [x] 注册路由到 `api/router.py`
- [x] 编写测试 `backend/tests/test_section_order_api.py`
  - [x] test_get_default_section_order
  - [x] test_update_section_order
  - [x] test_inherit_on_create
  - [x] test_reorder
  - [x] test_toggle_visible
  - [x] test_get_nonexistent_node

## 前端

- [x] 创建 `frontend/src/types/section.ts`
  - [x] SectionItem 类型（key, title, visible）
- [x] 创建 `frontend/src/components/section/SectionOrderPanel.tsx`
  - [x] 拖拽排序（HTML5 Drag API）
  - [x] 显示/隐藏开关
  - [x] 防抖保存 500ms
  - [x] 节点切换时重新加载
- [x] 添加 `getSectionOrder` / `updateSectionOrder` 到 `api.ts`
- [x] 集成到 `CenterPanel.tsx`（编辑器 Tab 工具栏下方）
- [x] 修改 `ResumePreview.tsx` 按 section_order 渲染

## 验证

- [x] 后端测试全部通过
- [x] 前端 typecheck 通过
- [x] HJ 人工验收
