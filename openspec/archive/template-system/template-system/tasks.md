# US-8: 简历预览与模板系统 — 任务清单

## 后端任务

### B1. 创建模板配置模块
- [ ] 新建 `backend/src/resume_agent/export/templates.py`
- [ ] 定义 `TemplateConfig` dataclass：`id / name / description / theme_color / accent_color / font_size_title / font_size_section / font_size_body / margin_mm / section_order`
- [ ] 定义 `TEMPLATES: dict[str, TemplateConfig]`，含 `modern` / `classic` / `tech` 三套配置
- [ ] 颜色参考模板分析报告：classic 用 `#1C487C`（天宫蓝），tech 用 `#0F766E`（薄荷绿），modern 保持 `#2563eb`

### B2. 重构 pdf_builder 为多模板
- [ ] `build_pdf(resume_data, job_title, company, template_id="modern")` 增加 `template_id` 参数
- [ ] 根据 `template_id` 获取 `TemplateConfig`，样式参数从 config 读取
- [ ] `modern` 模板：保持当前实现（分隔线 + 左对齐标题）
- [ ] `classic` 模板：色块标题条（Table 单元格背景色 + 白字标题），段落顺序 name→experience→projects→skills
- [ ] `tech` 模板：紧凑布局，技能以"标签"形式横排，项目经历突出 tech_stack
- [ ] 保留 `_escape_xml` / `_ensure_font_registered` 工具函数
- [ ] 未知 template_id 时回退到 modern 并 log warning

### B3. 新增 templates API 端点
- [ ] 新建 `backend/src/resume_agent/api/templates.py`
- [ ] `GET /templates` 返回模板列表（id / name / description / theme_color）
- [ ] 在 `router.py` 中注册 templates router

### B4. 修改 export API
- [ ] `ExportRequest` 增加 `template_id: str = "modern"` 字段
- [ ] `export_pdf` 将 `template_id` 传给 `build_pdf`

### B5. 后端测试
- [ ] `test_templates_api.py`：GET /api/templates 返回 3 个模板，字段齐全
- [ ] `test_export_api.py` 扩展：
  - 导出 classic 模板 PDF，验证 magic bytes + 中文可提取
  - 导出 tech 模板 PDF，验证 magic bytes + 中文可提取
  - 未知 template_id 回退 modern 不报错
  - 不同模板生成的 PDF 字节数不同（验证模板确实有差异）

## 前端任务

### F1. 类型定义
- [ ] 新建 `frontend/src/types/template.ts`：`TemplateInfo`（id / name / description / theme_color）
- [ ] 在 `api.ts` 增加 `getTemplates()` 函数

### F2. 模板选择器组件
- [ ] 新建 `frontend/src/components/template/TemplateSelector.tsx`
- [ ] 卡片式横向列表，每张卡片：模板名 + 主题色色块 + 描述
- [ ] 选中态高亮（边框变色），点击触发 `onSelect(templateId)`

### F3. 简历预览组件
- [ ] 新建 `frontend/src/components/template/ResumePreview.tsx`
- [ ] 接收 `resumeData` + `templateId`，用 CSS 模拟 PDF 布局渲染
- [ ] `modern`：简洁分隔线风格
- [ ] `classic`：色块标题条风格（白字在彩色背景上）
- [ ] `tech`：紧凑标签风格（技能横排）
- [ ] 无数据时显示空状态提示

### F4. 集成到 CenterPanel
- [ ] 将"编辑器"Tab 从占位改为渲染 `TemplateSelector` + `ResumePreview`
- [ ] 模板选择状态用 useState 管理
- [ ] 预览数据来源：从 GenerateView 传入 AI 生成结果（通过 RightPanel → MainLayout → CenterPanel）

### F5. 导出联动
- [ ] `exportResumePDF` 函数增加 `templateId` 参数
- [ ] `GenerateView` 的导出按钮传入当前选中模板

### F6. 前端验证
- [ ] `pnpm typecheck` 通过
- [ ] `pnpm build` 通过
- [ ] 无未使用的导入/变量
