# US-15: 信息完整性检测 + 可编辑预览 - 任务清单

## 后端

- [ ] 创建 `api/completeness.py`
  - [ ] `POST /completeness/check` 端点
  - [ ] `PUT /tree/node/{node_id}/section` 段落编辑端点
- [ ] 注册路由到 router.py
- [ ] 编写测试 `tests/test_completeness_api.py`

## 前端

- [ ] 创建 `lib/completeness.ts` 完整性检测逻辑
- [ ] 修改 `ResumePreview.tsx` — 段落可点击编辑
  - [ ] summary 可编辑
  - [ ] experience/projects 每条可编辑
  - [ ] skills 可编辑
- [ ] 创建 `components/completeness/CompletenessBar.tsx` 评分条
- [ ] 缺失字段高亮标注
- [ ] 检测清单可点击跳转
- [ ] 添加 `updateSection` 到 api.ts

## 验证

- [ ] 后端测试通过
- [ ] 前端 typecheck 通过
- [ ] HJ 人工验收
