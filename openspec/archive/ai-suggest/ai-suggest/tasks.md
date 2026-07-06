# US-9: AI 智能补全 — 任务清单

## 后端任务

### B1. 创建 suggest 端点
- [ ] 新建 `backend/src/resume_agent/api/suggest.py`
- [ ] `SuggestRequest` 模型：structured_jd / section / content / gap_report(可选)
- [ ] `POST /suggest` 端点

### B2. 识别内容不足字段
- [ ] `_find_thin_fields(section, content)` → 返回不足字段列表
- [ ] experience: highlights < 2 条 → 不足
- [ ] projects: description < 20 字 或 tech_stack 为空 → 不足
- [ ] skills: 某 context 为空 → 不足

### B3. 定向检索 + LLM 生成建议
- [ ] 对不足字段，用 JD 技能词在知识库检索补充素材
- [ ] LLM 基于检索素材生成建议文本
- [ ] 限制 ≤ 3 条建议
- [ ] LLM 未配置 / 知识库为空 → 返回空列表

### B4. 注册路由
- [ ] 在 `router.py` 注册 suggest router

### B5. 后端测试
- [ ] `test_suggest_api.py`：
  - 不足字段识别（highlights < 2）
  - 知识库为空返回空建议
  - LLM 未配置返回空建议
  - 建议数量 ≤ 3
  - 完整请求返回结构正确

## 前端任务

### F1. 类型定义
- [ ] 新建 `frontend/src/types/suggest.ts`：Suggestion / SuggestResult

### F2. API 封装
- [ ] `api.ts` 增加 `generateSuggestions()` 函数

### F3. 建议卡片组件
- [ ] 新建 `frontend/src/components/generate/SuggestionCards.tsx`
- [ ] 每条建议：内容 + 来源 + 原因 + 采纳/忽略按钮
- [ ] 采纳后回调 `onAccept(suggestion)`
- [ ] 忽略后回调 `onDismiss(index)`

### F4. 集成到 GenerateView
- [ ] 生成完成后自动调用 suggest API
- [ ] 建议卡片显示在生成结果下方
- [ ] 采纳后将内容追加到 result.content 对应字段

### F5. 前端验证
- [ ] pnpm typecheck 通过
- [ ] pnpm build 通过
