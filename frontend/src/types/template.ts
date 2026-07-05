// frontend/src/types/template.ts
// 模板系统相关类型（US-8）

/** GET /api/templates 返回的单个模板信息 */
export interface TemplateInfo {
  /** 模板唯一标识，如 "modern" / "classic" / "tech" */
  id: string;
  /** 模板中文名称，如 "现代简约" */
  name: string;
  /** 模板简短描述 */
  description: string;
  /** 主题色（hex 字符串），用于标题条 / 分隔线 / 选中态 */
  theme_color: string;
}
