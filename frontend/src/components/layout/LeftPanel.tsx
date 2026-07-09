// frontend/src/components/layout/LeftPanel.tsx
// 左栏：品牌区 + 导航列表（精简为 3 项，badge 动态化）
//       + 上传区（简历+知识素材）+ 知识库状态
//
// US-21：移除无功能导航项，badge 从后端动态获取，activeView 同步

import { useState } from 'react';
import UploadZone from '@/components/common/UploadZone';
import KnowledgeStatus from '@/components/common/KnowledgeStatus';
import PersonalInfoForm from '@/components/personal/PersonalInfoForm';
import SectionOrderPanel from '@/components/section/SectionOrderPanel';
import { uploadKnowledge } from '@/lib/api';
import type { ActiveView } from '@/types/knowledge';
import type { SectionItem } from '@/types/section';
import type { ResumeNode } from '@/types/tree';

/** 导航项：label 为展示文案，view 为对应的中栏视图 */
interface NavItem {
  label: string;
  icon: string;
  view: ActiveView;
  /** 动态 badge 数字，undefined 时不显示 */
  badge?: number;
}

const NAV_ICONS: Record<string, React.ReactNode> = {
  overview: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="1" y="1" width="14" height="14" rx="2" />
      <path d="M5 1v14M1 5h14" />
    </svg>
  ),
  tree: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="4" cy="8" r="2.5" />
      <circle cx="12" cy="4" r="2.5" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6.5 7.2l3.5-2M6.5 8.8l3.5 2" />
    </svg>
  ),
  kb: (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 2l1.5 3H14l-2.5 2 1 3.5L8 8.5 3.5 10.5l1-3.5L2 5h4.5z" />
    </svg>
  ),
};

interface LeftPanelProps {
  /** 简历上传+解析成功后触发，用于刷新版本树 */
  onTreeRefresh?: () => void;
  /** 知识素材上传成功后触发，用于刷新 KnowledgeStatus */
  onKnowledgeRefresh?: () => void;
  /** KnowledgeStatus 的刷新 key，变化时重新拉取 stats */
  knowledgeRefreshKey?: number;
  /** 导航项点击回调，通知父组件切换中栏视图 */
  onNavigate?: (view: ActiveView) => void;
  /** 当前激活的视图（用于同步导航高亮） */
  activeView?: ActiveView;
  /** 版本树节点列表（用于计算分支 badge 数字） */
  treeNodes?: ResumeNode[];
  /** 当前选中的版本树节点 ID（US-12 个人信息） */
  selectedNodeId?: string | null;
  /** US-13: section_order 保存后通知外部更新 selectedNode */
  onSectionOrderUpdated?: (sections: SectionItem[]) => void;
  /** 右栏是否收起 */
  rightPanelCollapsed?: boolean;
  /** 切换右栏收起/展开 */
  onToggleRightPanel?: (collapsed: boolean) => void;
}

export default function LeftPanel({
  onTreeRefresh,
  onKnowledgeRefresh,
  knowledgeRefreshKey = 0,
  onNavigate,
  activeView = 'version-tree',
  treeNodes = [],
  selectedNodeId = null,
  onSectionOrderUpdated,
  rightPanelCollapsed = false,
  onToggleRightPanel,
}: LeftPanelProps) {
  // 知识库文档数（从 KnowledgeStatus 回调获取）
  const [knowledgeDocCount, setKnowledgeDocCount] = useState(0);

  // 动态计算 badge
  const branchCount = treeNodes.filter((n) => n.node_type !== 'master').length;

  const navItems: NavItem[] = [
    { label: '总览面板', icon: 'overview', view: 'version-tree' },
    { label: '简历版本分支', icon: 'tree', view: 'version-tree', badge: branchCount },
    { label: '个人知识库', icon: 'kb', view: 'knowledge', badge: knowledgeDocCount },
  ];

  // 根据 activeView 决定高亮项
  // 右栏收起时高亮"简历版本分支"，展开时高亮"总览面板"
  const activeLabel =
    activeView === 'knowledge' ? '个人知识库'
      : rightPanelCollapsed ? '简历版本分支'
      : '总览面板';

  function handleNavClick(item: NavItem) {
    onNavigate?.(item.view);
    // "简历版本分支" → 收起右栏；"总览面板" → 展开右栏
    if (item.label === '简历版本分支') {
      onToggleRightPanel?.(true);
    } else if (item.label === '总览面板') {
      onToggleRightPanel?.(false);
    }
  }

  return (
    <aside
      className="flex flex-col overflow-y-auto bg-bg-secondary border-r border-border-default"
      style={{ width: 'var(--left-panel-width)', minWidth: 'var(--left-panel-width)' }}
    >
      {/* Logo area */}
      <div className="px-5 pt-5 pb-4 border-b border-border-subtle">
        <div className="flex items-center gap-2 mb-1">
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={{ color: 'var(--color-brand-primary)' }}
          >
            <line x1="6" y1="3" x2="6" y2="15" />
            <circle cx="18" cy="6" r="3" />
            <circle cx="6" cy="18" r="3" />
            <path d="M18 9a9 9 0 0 1-9 9" />
          </svg>
          <span className="font-bold text-lg tracking-tight">Resume-Agent</span>
        </div>
        <div className="text-xs text-text-tertiary ml-7">智能简历工作台</div>
      </div>

      {/* Navigation */}
      <nav className="p-2 px-3">
        {navItems.map((item) => (
          <div
            key={item.label}
            onClick={() => handleNavClick(item)}
            className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer transition-all mb-0.5 border-l-2 text-sm ${
              activeLabel === item.label
                ? 'bg-brand-primary-muted text-brand-primary border-brand-primary font-medium'
                : 'text-text-secondary border-transparent hover:bg-bg-hover hover:text-text-primary'
            }`}
          >
            <span
              className="w-4 h-4 flex-shrink-0"
              style={{ opacity: activeLabel === item.label ? 1 : 0.7 }}
            >
              {NAV_ICONS[item.icon]}
            </span>
            <span>{item.label}</span>
            {item.badge !== undefined && item.badge > 0 && (
              <span
                className={`ml-auto font-mono text-xs px-2 rounded-full min-w-[20px] text-center ${
                  activeLabel === item.label
                    ? 'bg-brand-primary text-white'
                    : 'bg-bg-elevated text-text-tertiary'
                }`}
              >
                {item.badge}
              </span>
            )}
          </div>
        ))}
      </nav>

      {/* Upload zones */}
      <div className="px-4 py-4 flex flex-col gap-3">
        <UploadZone
          title="拖入旧简历 (PDF/Word)"
          hint="自动解析并创建初始版本"
          onFileUploaded={() => onTreeRefresh?.()}
        />
        <UploadZone
          title="注入知识素材 (周报/论文/CTF/博客)"
          hint="丰富个人知识库以优化简历"
          accept=".pdf,.docx,.md,.txt"
          uploadFn={uploadKnowledge}
          parseFn={null}
          successText="已注入知识库"
          invalidTypeMessage="仅支持 PDF / Word / Markdown / TXT 文件"
          onFileUploaded={() => onKnowledgeRefresh?.()}
          icon={
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="12" y1="18" x2="12" y2="12" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          }
        />
      </div>

      {/* Personal info form (US-12) */}
      <PersonalInfoForm nodeId={selectedNodeId} />

      {/* Section order panel (US-13) */}
      <SectionOrderPanel nodeId={selectedNodeId} onOrderUpdated={onSectionOrderUpdated} />

      {/* Knowledge base status */}
      <KnowledgeStatus
        refreshKey={knowledgeRefreshKey}
        onStatsLoaded={(stats) => setKnowledgeDocCount(stats.document_count)}
      />
    </aside>
  );
}
