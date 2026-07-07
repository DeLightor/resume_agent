# US-10: 版本 Diff 对比 — 任务清单

## 后端任务

### B1. 创建 diff 端点
- [ ] 新建 `backend/src/resume_agent/api/diff.py`
- [ ] `DiffRequest` 模型：node_a_id / node_b_id
- [ ] `POST /diff` 端点（prefix="/diff"）
- [ ] 从 resume_versions 表读取两个节点的 content_json

### B2. 实现字段级 Diff
- [ ] `_diff_experience(list_a, list_b)` → 按 company+role 匹配，返回 added/removed/modified
- [ ] `_diff_projects(list_a, list_b)` → 按 name 匹配，返回 added/removed/modified
- [ ] `_diff_skills(skills_a, skills_b)` → 按 category+name 匹配，返回 added/removed/modified
- [ ] `_compute_diff(content_a, content_b)` → 汇总三段 diff + 统计 summary

### B3. 注册路由
- [ ] 在 `router.py` 注册 diff router

### B4. 后端测试
- [ ] `test_diff_api.py`：
  - 两节点相同返回空 diff
  - 新增经历（added）
  - 删除项目（removed）
  - 修改技能 context（modified）
  - content_json 为 null 不报错
  - 节点不存在返回 404
  - 完整三段对比

## 前端任务

### F1. 类型定义
- [ ] 新建 `frontend/src/types/diff.ts`：DiffItem / DiffSection / DiffResult / DiffSummary

### F2. API 封装
- [ ] `api.ts` 增加 `getNodeDiff(nodeAId, nodeBId)` 函数

### F3. Diff 视图组件
- [ ] 新建 `frontend/src/components/diff/DiffView.tsx`
- [ ] 顶部：两个节点选择器（下拉框）
- [ ] 中部：三段折叠面板
- [ ] 差异项颜色高亮：绿/红/黄
- [ ] 差异内容可复制

### F4. 集成到 CenterPanel
- [ ] "Diff 对比" Tab 从占位改为渲染 DiffView
- [ ] 从 tree state 传入节点列表

### F5. 前端验证
- [ ] pnpm typecheck 通过
- [ ] pnpm build 通过
