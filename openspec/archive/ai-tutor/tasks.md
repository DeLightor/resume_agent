# US-11: AI 导师学习建议 - 任务清单

## 后端

- [ ] 创建 `backend/src/resume_agent/api/tutor.py`
  - [ ] 定义 `TutorRequest` / `TutorSuggestion` / `LearningPath` / `Resource` Pydantic 模型
  - [ ] 实现 `POST /tutor/suggest` 端点
  - [ ] 实现 `_generate_suggestions()` LLM 调用
  - [ ] LLM 未配置时返回模板化建议
  - [ ] JSON 解析失败兜底
- [ ] 注册路由到 `api/router.py`
- [ ] 编写测试 `backend/tests/test_tutor_api.py`
  - [ ] test_missing_skills_returned
  - [ ] test_partial_skills_returned
  - [ ] test_covered_skills_filtered_out
  - [ ] test_empty_items_returns_empty
  - [ ] test_llm_not_configured_fallback
  - [ ] test_llm_json_parse_fallback
  - [ ] test_max_skills_limit
  - [ ] test_response_structure

## 前端

- [ ] 创建 `frontend/src/types/tutor.ts`
  - [ ] TutorSuggestion / LearningPath / TutorResource 类型
- [ ] 创建 `frontend/src/components/tutor/TutorView.tsx`
  - [ ] "获取学习建议"按钮（Gap 报告有 missing/partial 时显示）
  - [ ] 加载 / 错误 / 空状态
  - [ ] 技能卡片：学习路径三步 + 资源列表
  - [ ] 资源链接：类型图标 + 可点击标题
  - [ ] 状态选择器：已掌握 / 学习中 / 待开始
  - [ ] localStorage 状态持久化
- [ ] 添加 `getTutorSuggestions` 到 `api.ts`
- [ ] 集成到 `RightPanel.tsx`（Gap 报告下方）

## 验证

- [ ] 后端测试全部通过
- [ ] 前端 typecheck + build 通过
- [ ] HJ 人工验收
