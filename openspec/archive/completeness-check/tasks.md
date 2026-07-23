# US-15: 信息完整性检测 + 可编辑预览 - 任务清单

## 后端

- [x] 创建 `api/completeness.py`
  - [x] `POST /completeness/check` 端点
  - [x] `PUT /tree/node/{node_id}/section` 段落编辑端点
- [x] 注册路由到 router.py
- [x] 编写测试 `tests/test_completeness_api.py`

## 前端

- [x] 创建 `lib/completeness.ts` 完整性检测逻辑
- [x] 修改 `ResumePreview.tsx` — 段落可点击编辑
  - [x] summary 可编辑
  - [x] experience/projects 每条可编辑
  - [x] skills 可编辑
- [x] 创建 `components/completeness/CompletenessBar.tsx` 评分条
- [x] 缺失字段高亮标注
- [x] 检测清单可点击跳转
- [x] 添加 `updateSection` 到 api.ts

## 验证

- [x] 后端测试通过
- [x] 前端 typecheck 通过
- [x] HJ 人工验收
