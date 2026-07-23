# US-16: 模板系统配置化

## 概述

扩展 TemplateConfig schema，新增 3 套模板（极简白/双栏/学术风），前端模板选择器展示 6 套卡片。

## 提议变更

### 后端

**1. 扩展 TemplateConfig**

新增字段：
- `columns`: 栏数（1 或 2）
- `font_family`: 字体族
- `line_height`: 行高
- `section_spacing`: 段落间距
- `header_style`: 标题风格（"underline" / "color_block" / "minimal" / "academic"）

**2. 新增 3 套模板**

| id | 名称 | 描述 | 特点 |
|----|------|------|------|
| minimal | 极简白 | 单栏大量留白，无色块无分隔线 | margin 20mm，标题仅加粗 |
| two_column | 双栏 | 左栏联系方式+技能，右栏经历 | columns=2 |
| academic | 学术风 | 论文格式，Times New Roman，居中标题 | 衬线字体，正式排版 |

### 前端

- THEME_COLORS 新增 3 套颜色
- 模板选择器适配 6 套卡片
- ResumePreview 支持新模板的渲染风格

## 约束

- 不引入新依赖
- 复用现有 TemplateConfig dataclass
- 后端 PDF 渲染暂不改动（仅前端预览适配）
