# US-6 Tasks

## 后端

- [x] 重写 `api/generate.py`：实现 3 步工作流（检索 → 反思 → 撰写）
- [x] 实现知识库经历检索（复用 Chroma `query`，按 JD 技能逐项检索）
- [x] 实现反思审核 LLM 调用（检测套话/夸大/矛盾）
- [x] 实现撰写 LLM 调用（基于检索内容 + 反思结果生成段落）
- [x] 注册路由（替换桩实现）
- [x] 编写测试 `test_generate_api.py`

## 前端

- [x] 新增 `types/generate.ts`：GenerateResult 类型
- [x] 新增 `lib/api.ts`：`generateResume(structuredJD, gapReport, section)` 函数
- [x] 新增 `components/generate/GenerateView.tsx`：段落选择 + 生成 + 结果 + 反思
- [x] 集成到 `RightPanel.tsx`：替换空状态提示

## 验证

- [x] 后端测试全通过
- [x] 前端 typecheck + build 通过
- [x] HJ 人工验收
