## 1. 规格和评审
- [x] 对照 PRD US-34 验收标准与当前代码，编写 proposal 与 design
- [x] 向 HJ 汇报设计方案与技术选型，等待 HJ 评审确认并授权开工

## 2. 实现
- [x] 前端：在 `ResumePreview.tsx` 中实现基于 A4 宽高比（1:1.4142）的动态高度与页数计算
- [x] 前端：实现非侵入式 A4 分页线与页码指示标签（`pointer-events-none`）
- [x] 前端：实现目标页数选择（1页/2页）与超页预警横幅
- [x] 后端：编写 `test_export_pagination.py` 抽检 PDF 渲染器页数一致性

## 3. 验证和交付
- [x] 执行全量测试（后端 pytest + 前端 tsc --noEmit + build）
- [x] 记录测试与浏览器验证结果至 `verification.md`
- [x] 启动服务，交由 HJ 进行人工体验验收（2026-09-11 验证通过）
- [x] 获得 HJ 明确授权后归档变更并提交（2026-09-11 授权）
