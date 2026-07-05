# US-8: 简历预览与模板系统 — 设计文档

## 架构概览

```
简历数据 JSON（统一数据源）
    │
    ├── TemplateConfig (modern / classic / tech)
    │     ├── theme_color
    │     ├── font sizes
    │     ├── margin
    │     └── section renderer
    │
    ├── 后端 PDF 渲染（reportlab）
    │     └── build_pdf(resume_data, template_id)
    │
    └── 前端 HTML 预览（CSS 模拟）
          └── ResumePreview(resumeData, templateId)
```

## 后端设计

### TemplateConfig 数据结构

```python
@dataclass
class TemplateConfig:
    id: str                    # "modern" / "classic" / "tech"
    name: str                  # "现代简约"
    description: str           # 简短描述
    theme_color: str           # "#2563eb"
    accent_color: str          # 强调色
    section_title_color: str   # 段落标题色
    use_color_block: bool      # classic=True, others=False
    margin_mm: float           # 页边距
    font_size_name: int        # 姓名字号
    font_size_section: int     # 段落标题字号
    font_size_body: int        # 正文字号
```

### 三套模板配置

| 属性 | modern | classic | tech |
|------|--------|---------|------|
| theme_color | #2563eb | #1C487C | #0F766E |
| use_color_block | False | True | False |
| margin_mm | 15 | 12.7 | 10 |
| font_size_name | 18 | 20 | 16 |
| font_size_section | 11 | 12 | 10 |
| font_size_body | 9 | 9 | 8.5 |
| 特色 | 分隔线 | 色块标题条 | 紧凑标签 |

### classic 模板色块标题条实现

使用 reportlab Table 作为标题条容器：
```python
from reportlab.platypus import Table, TableStyle

def _build_section_header(text: str, config: TemplateConfig) -> Table:
    """色块标题条：白字在彩色背景上。"""
    table = Table([[Paragraph(text, white_style)]], colWidths=[full_width])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor(config.theme_color)),
        ('TEXTCOLOR', (0, 0), (-1, -1), white),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return table
```

### tech 模板技能标签实现

技能以逗号分隔横排，用浅色背景块包裹：
```python
def _build_skill_tags(skills: list[str], config: TemplateConfig) -> str:
    """技能标签横排 HTML（reportlab Paragraph 支持）。"""
    tags = [f'<font backColor="#E8F5E9">{s}</font>' for s in skills]
    return ' '.join(tags)
```

## 前端设计

### ResumePreview 组件结构

```tsx
interface ResumePreviewProps {
  resumeData: Record<string, unknown> | null;
  templateId: string;
}

// 根据 templateId 选择 CSS 类名前缀
// modern: "preview-modern" → 简洁分隔线
// classic: "preview-classic" → 色块标题条
// tech: "preview-tech" → 紧凑标签
```

### 模板 CSS 差异

```css
/* modern: 简洁分隔线 */
.preview-modern .section-title {
  border-bottom: 1px solid #e5e7eb;
  color: #1a1a1a;
}

/* classic: 色块标题条 */
.preview-classic .section-title {
  background-color: #1C487C;
  color: white;
  padding: 4px 8px;
}

/* tech: 紧凑标签 */
.preview-tech .skill-tag {
  display: inline-block;
  background-color: #E8F5E9;
  padding: 2px 6px;
  margin: 2px;
  font-size: 11px;
}
```

### 数据流

```
RightPanel (GenerateView 生成结果)
    │
    ▼
MainLayout (状态提升：resumeData + templateId)
    │
    ├── CenterPanel (编辑器 Tab)
    │     └── TemplateSelector + ResumePreview
    │
    └── RightPanel (GenerateView)
          └── 导出 PDF 时传入 templateId
```

由于 GenerateView 在 RightPanel 中，CenterPanel 需要获取生成结果，方案：
- 在 MainLayout 中用 useState 管理 `generatedResumeData`
- GenerateView 生成成功后通过回调 `onGenerated(data)` 写入 MainLayout
- CenterPanel 的编辑器 Tab 从 props 读取 `generatedResumeData` + `templateId`

## 约束与决策

1. **不引入新依赖**：仅用 reportlab 内置能力（Table / Paragraph / Drawing）实现色块
2. **预览不要求像素一致**：HTML 与 reportlab 渲染引擎不同，承诺"结构一致"而非"像素一致"
3. **模板配置为常量**：不存数据库，不动态加载，硬编码在 `templates.py`
4. **向后兼容**：`template_id` 参数可选，默认 `modern`，US-7 的调用不受影响
