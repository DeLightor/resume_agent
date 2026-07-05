// frontend/src/components/common/Breadcrumb.tsx
// 动态路径面包屑：由 CenterPanel 从选中节点回溯 parent_id 链生成

interface BreadcrumbProps {
  /** 路径段数组，未传入时默认 ['master'] */
  path?: string[];
}

export default function Breadcrumb({ path = ['master'] }: BreadcrumbProps) {
  return (
    <nav className="flex items-center gap-2 text-sm">
      {path.map((seg, i) => (
        <span key={`${i}-${seg}`} className="flex items-center gap-2">
          {i > 0 && <span className="text-text-muted text-xs">/</span>}
          <span
            className={
              i === path.length - 1
                ? 'text-text-primary font-medium cursor-pointer'
                : 'text-text-secondary cursor-pointer hover:text-brand-primary transition-colors'
            }
          >
            {seg}
          </span>
        </span>
      ))}
    </nav>
  );
}
