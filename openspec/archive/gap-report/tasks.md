# US-5 Tasks

## 后端

- [x] 新增 `api/gap_report.py`：`POST /api/gap-report` 端点
- [x] 实现 `_search_skill_in_kb(skill: str) -> list[dict]`：调用 Chroma 检索单项技能
- [x] 实现 `_determine_status(score: float) -> str`：三色判定逻辑
- [x] 实现 LLM 批量生成描述（单次调用处理所有技能项）
- [x] 注册路由到 `main.py`
- [x] 编写测试 `test_gap_report_api.py`：空知识库、全覆盖、部分覆盖、LLM 异常

## 前端

- [x] 新增 `types/gap.ts`：GapReport / GapItem 类型
- [x] 新增 `lib/api.ts`：`generateGapReport(structuredJD)` 函数
- [x] 新增 `components/gap/GapReportView.tsx`：匹配度圆环 + 汇总 + 列表
- [x] 集成到 `RightPanel.tsx`：JD 分析后显示"生成 Gap 报告"按钮

## 验证

- [x] 后端测试全通过
- [x] 前端 typecheck + build 通过
- [x] HJ 人工验收
