# Proposal: jd-screenshot-analysis

## 概述

实现 US-4 JD 截图分析功能：用户上传招聘截图（PNG/JPG），系统通过 MinerU API 提取文本，再用 DeepSeek LLM 结构化提取技术栈、硬技能、软技能、加分项，右栏展示 JD 卡片。

## 技术方案

```
用户上传截图 → MinerU API（图片→Markdown 文本）→ DeepSeek（结构化提取）→ JD 卡片
```

### MinerU API 流程
1. `POST /api/v4/file-urls/batch` 申请上传链接
2. `PUT` 上传图片到返回的 URL
3. 系统自动创建解析任务
4. `GET /api/v4/extract/task/{task_id}` 轮询直到 state=done
5. 下载 `full_zip_url` 的 zip → 提取 `full.md`

### DeepSeek 结构化提取
- Prompt：将 OCR 文本转为 `{tech_stack, hard_skills, soft_skills, bonus_items}` JSON
- 复用已有 `LLMClient`

## 变更范围

### 后端
1. `config.py`：新增 `mineru_api_token`、`mineru_api_base` 配置
2. 新建 `parsers/mineru_client.py`：MinerU API 客户端（上传→轮询→下载→提取 Markdown）
3. 新建 `api/jd.py`：`POST /api/jd/analyze` 端点
4. 测试：mock MinerU API 响应

### 前端
1. 新建 `src/types/jd.ts`：JD 分析结果类型
2. `api.ts`：新增 `analyzeJD(file)` 
3. 新建 `src/components/jd/JDUploadZone.tsx`：截图上传区
4. 新建 `src/components/jd/JDCard.tsx`：结构化结果展示卡片
5. `RightPanel.tsx`：集成 JD 卡片
6. `MainLayout.tsx`：导航切换 + 状态管理

## 验收标准
- 支持 PNG、JPG 格式上传
- MinerU 提取截图文本
- DeepSeek 结构化提取技术栈/硬技能/软技能/加分项
- 右栏 JD 卡片展示，支持编辑
- 截图提取失败提示重新上传
- 单张截图提取 ≤ 15s
