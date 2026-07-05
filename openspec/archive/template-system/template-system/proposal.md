# US-8: 简历预览与模板系统

## 概述

将单一 PDF 渲染器重构为多模板架构，支持至少 3 套内置模板（现代简约 / 经典学术 / 大厂技术），前端提供模板选择器与实时预览，实现"数据与排版分离，所见即所得"。

## 动机

MVP 阶段（US-7）的 PDF 导出只有一套硬编码的 modern 模板，用户无法选择排版风格。真实求职场景中，不同岗位/公司偏好不同简历风格（技术岗偏简洁分栏，学术岗偏经典正式，大厂岗偏色块标题条）。基于用户提供的 45 份真实简历模板分析，4 套"爆款"模板共用同一布局仅颜色不同，可抽象为"色块标题条"模板 + 可配置主题色。

## 提议变更

### 后端：多模板架构

1. **重构 `pdf_builder.py`**：抽取 `TemplateConfig` 数据类（主题色 / 字体 / 间距 / 段落顺序），`build_pdf()` 接收 `template_id` 参数选择模板配置。
2. **内置 3 套模板**：
   - `modern`（现代简约）：当前实现，灰蓝色调，简洁分隔线
   - `classic`（经典学术）：色块标题条（复刻爆款系列），白字标题在彩色块上
   - `tech`（大厂技术）：紧凑分栏，强调技术栈标签
3. **新增 `GET /api/templates`**：返回模板列表（id / name / description / thumbnail_color）
4. **修改 `POST /api/export/pdf`**：增加可选 `template_id` 参数，默认 `modern`

### 前端：模板选择器 + 预览

1. **模板选择器**：卡片式横向列表，每张卡片显示模板名 + 主题色色块 + 简短描述，点击切换。
2. **简历预览组件 `ResumePreview`**：基于 AI 生成结果（experience / projects / skills）+ 选中模板，渲染 HTML 预览（模拟 PDF 布局）。
3. **集成到 CenterPanel**：将"编辑器"Tab 从占位改为实际渲染 ResumePreview + 模板选择器。
4. **导出联动**：导出 PDF 时传入当前选中的 `template_id`，确保预览与 PDF 一致。

## 端点

### `GET /api/templates`

响应：
```json
{
  "ok": true,
  "data": [
    {
      "id": "modern",
      "name": "现代简约",
      "description": "简洁分隔线，灰蓝色调，适合大多数岗位",
      "theme_color": "#2563eb"
    },
    {
      "id": "classic",
      "name": "经典学术",
      "description": "色块标题条，正式严谨，适合学术/传统行业",
      "theme_color": "#1C487C"
    },
    {
      "id": "tech",
      "name": "大厂技术",
      "description": "紧凑布局，技术栈标签突出，适合技术岗",
      "theme_color": "#0F766E"
    }
  ]
}
```

### `POST /api/export/pdf`（修改）

请求体新增 `template_id` 字段：
```json
{
  "resume_data": { ... },
  "job_title": "推荐算法工程师",
  "company": "腾讯",
  "template_id": "classic"
}
```

## 约束

- 所有模板生成的 PDF 文本必须可选可解析（ATS 友好）
- 所有模板使用 STSong-Light CJK 字体（无外部字体依赖）
- 预览为 HTML 渲染（CSS 模拟 PDF 布局），不要求像素级一致，但段落结构/顺序/配色一致
- 不引入新的后端依赖（仅用 reportlab + FastAPI）
- 模板配置为 Python 字典常量，无需数据库存储

## 风险

- 预览（HTML）与 PDF（reportlab）渲染引擎不同，无法完全像素一致 → 约束为"结构一致"，不承诺像素级 WYSIWYG
- reportlab 色块标题条需用 Table 或 Drawing Flowable 实现，比纯 Paragraph 复杂 → 用 Table 单元格背景色方案
