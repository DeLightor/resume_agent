// frontend/src/components/template/TemplateSelector.tsx
// 模板选择器（US-8）
// 卡片式横向列表，每张卡片显示：模板名 + 主题色圆点 + 描述
// 选中态：边框变为主题色 + 背景轻微着色
// 未选中态：灰色边框 hover 变色

import type { TemplateInfo } from '@/types/template';

interface TemplateSelectorProps {
  /** 后端返回的模板列表（或 fallback） */
  templates: TemplateInfo[];
  /** 当前选中的模板 id */
  selectedId: string;
  /** 选中模板时回调 */
  onSelect: (id: string) => void;
}

export default function TemplateSelector({
  templates,
  selectedId,
  onSelect,
}: TemplateSelectorProps) {
  return (
    <div className="flex gap-2 overflow-x-auto">
      {templates.map((tpl) => {
        const selected = tpl.id === selectedId;
        return (
          <button
            key={tpl.id}
            type="button"
            onClick={() => onSelect(tpl.id)}
            className="flex-shrink-0 w-44 text-left rounded-md border p-2.5 cursor-pointer transition-all font-body"
            style={{
              borderColor: selected ? tpl.theme_color : 'var(--color-border-default)',
              backgroundColor: selected
                ? `${tpl.theme_color}14`
                : 'transparent',
              boxShadow: selected ? `0 0 0 1px ${tpl.theme_color}` : 'none',
            }}
          >
            {/* 顶部：模板名 + 主题色圆点 */}
            <div className="flex items-center gap-2 mb-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: tpl.theme_color }}
              />
              <span
                className="text-sm font-medium"
                style={{
                  color: selected
                    ? tpl.theme_color
                    : 'var(--color-text-primary)',
                }}
              >
                {tpl.name}
              </span>
            </div>
            {/* 描述 */}
            <div className="text-[11px] text-text-tertiary leading-snug">
              {tpl.description}
            </div>
          </button>
        );
      })}
    </div>
  );
}
