# Tasks: jd-screenshot-analysis

## 后端
- [x] config.py：新增 mineru_api_token、mineru_api_base 字段
- [x] 新建 parsers/mineru_client.py：MinerU API 客户端
  - upload_file(file_path) → batch_id, task_id
  - poll_task(task_id) → state, full_zip_url
  - download_and_extract(zip_url) → markdown text
  - extract_text_from_image(file_path) → str（全流程封装）
- [x] 新建 api/jd.py：POST /api/jd/analyze
  - 接收 UploadFile（png/jpg）
  - 保存到 files/jd/{uuid}.{ext}
  - 调用 mineru_client.extract_text_from_image
  - 调用 LLMClient 结构化提取（tech_stack/hard_skills/soft_skills/bonus_items）
  - 返回结构化 JD 数据
- [x] 测试：mock MinerU API + mock LLM，测试完整流程

## 前端
- [x] 新建 types/jd.ts：JDAnalysisResult 类型
- [x] api.ts：新增 analyzeJD(file)
- [x] 新建 components/jd/JDUploadZone.tsx：截图拖拽上传
- [x] 新建 components/jd/JDCard.tsx：结构化结果展示（可编辑）
- [x] RightPanel.tsx：集成 JD 卡片
- [x] MainLayout.tsx：导航切换到 JD 分析时展示上传区

## 验证
- [x] 后端 pytest + ruff
- [x] 前端 typecheck + build
