// frontend/src/components/layout/MainLayout.tsx
// 三栏 flex 布局容器：左 260px / 中 flex-1 / 右 380px
// 在此层持有 treeRefreshKey / knowledgeRefreshKey / activeView 状态：
// - treeRefreshKey：简历上传成功 → 中栏版本树刷新
// - knowledgeRefreshKey：知识素材上传 / 文档删除 → KnowledgeStatus + KnowledgeView 刷新
// - activeView：从 Workspace 传入（GlobalToolbar + LeftPanel 共享）
//
// US-21：activeView 提升到 Workspace 层，treeNodes 传给 LeftPanel 用于 badge
// v1.4: rightPanelCollapsed — 点击"简历版本分支"时收起右栏，给中栏更多空间

import { useCallback, useState } from 'react';
import LeftPanel from './LeftPanel';
import CenterPanel from './CenterPanel';
import RightPanel from './RightPanel';
import type { ActiveView } from '@/types/knowledge';
import type { ResumeNode } from '@/types/tree';
import type { GapReport } from '@/types/gap';

interface MainLayoutProps {
  /** 当前激活的视图（从 Workspace 传入） */
  activeView: ActiveView;
  /** 导航切换回调（从 Workspace 传入） */
  onNavigate: (view: ActiveView) => void;
  /** 右栏是否收起 */
  rightPanelCollapsed: boolean;
  /** 切换右栏收起/展开 */
  onToggleRightPanel: (collapsed: boolean) => void;
  /** 导航计数器：每次点击导航递增，用于强制重置中栏 activeTab */
  navKey: number;
}

/** US-29：待自动发送的快捷指令（MainLayout → CenterPanel → AgentWorkbench） */
export interface PendingAsk {
  /** 带最新工作台上下文组装的 context */
  context: Record<string, unknown>;
  /** 首条消息 */
  prompt: string;
}

export default function MainLayout({
  activeView,
  onNavigate,
  rightPanelCollapsed,
  onToggleRightPanel,
  navKey,
}: MainLayoutProps) {
  // 上传成功后递增，触发 VersionTree 重新拉取
  const [treeRefreshKey, setTreeRefreshKey] = useState(0);
  // 知识库上传 / 删除后递增，触发 KnowledgeStatus + KnowledgeView 刷新
  const [knowledgeRefreshKey, setKnowledgeRefreshKey] = useState(0);
  // US-8：AI 生成的简历数据（右栏 GenerateView 产出 → 中栏 ResumePreview 展示）
  const [generatedResumeData, setGeneratedResumeData] = useState<
    Record<string, unknown> | null
  >(null);
  // US-8：当前选中的模板 id（默认 modern）
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('modern');
  // 版本树节点列表（供 Diff 选择器和保存功能使用 + LeftPanel badge）
  const [treeNodes, setTreeNodes] = useState<ResumeNode[]>([]);
  // US-12：当前选中的节点 ID（传给左栏 PersonalInfoForm）
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  /** US-13: section_order 更新后通知 CenterPanel 刷新 selectedNode 的 content_json */
  const [sectionOrderVersion, setSectionOrderVersion] = useState(0);
  /** US-14: JD 分析结果（结构化），用于一键生成 */
  const [structuredJD, setStructuredJD] = useState<Record<string, unknown> | null>(null);
  /** US-29：Gap 报告提升（供 AI 快捷指令组装上下文） */
  const [gapReport, setGapReport] = useState<GapReport | null>(null);
  /** US-29：待自动发送的快捷指令（切到 AI 视图后由 AgentWorkbench 消费） */
  const [pendingAsk, setPendingAsk] = useState<PendingAsk | null>(null);

  const handleTreeRefresh = useCallback(() => {
    setTreeRefreshKey((k) => k + 1);
  }, []);

  const handleKnowledgeRefresh = useCallback(() => {
    setKnowledgeRefreshKey((k) => k + 1);
  }, []);

  // AI 生成成功后写入 generatedResumeData，供中栏预览
  const handleResumeGenerated = useCallback(
    (data: Record<string, unknown>) => {
      setGeneratedResumeData(data);
    },
    [],
  );

  // 模板切换
  const handleTemplateSelect = useCallback((id: string) => {
    setSelectedTemplateId(id);
  }, []);

  // 版本树节点列表更新（CenterPanel 加载树数据时回灌）
  const handleTreeNodesUpdate = useCallback((nodes: ResumeNode[]) => {
    setTreeNodes(nodes);
  }, []);

  /**
   * US-29：组装工作台上下文（供 Agent 对话注入）。
   * - structured_jd 只保留五个结构化字段（不传 raw_text，控制 token）
   * - gap_report 转摘要（overall_score + 三色计数 + missing 技能列表）
   */
  const buildAgentContext = useCallback((): Record<string, unknown> => {
    const ctx: Record<string, unknown> = {};
    if (selectedNodeId) ctx.current_node_id = selectedNodeId;
    if (structuredJD) {
      const jd = structuredJD as Record<string, unknown>;
      const trimmed: Record<string, unknown> = {};
      for (const key of [
        'job_title', 'tech_stack', 'hard_skills', 'soft_skills', 'bonus_items',
      ]) {
        if (jd[key] != null) trimmed[key] = jd[key];
      }
      if (Object.keys(trimmed).length > 0) ctx.structured_jd = trimmed;
    }
    if (gapReport) {
      const missing = gapReport.items
        .filter((item) => item.status === 'missing')
        .map((item) => item.skill)
        .slice(0, 8);
      ctx.gap_summary = {
        overall_score: gapReport.overall_score,
        missing,
        missing_count: missing.length,
      };
    }
    return ctx;
  }, [selectedNodeId, structuredJD, gapReport]);

  /** US-29：AI 快捷指令 → 切 AI 视图 + 带上下文自动发送 */
  const handleQuickAsk = useCallback(
    (prompt: string) => {
      setPendingAsk({ context: buildAgentContext(), prompt });
      onNavigate('agent');
    },
    [buildAgentContext, onNavigate],
  );

  return (
    <div
      className="flex overflow-hidden"
      style={{ height: 'calc(100vh - var(--header-height))' }}
    >
      <LeftPanel
        onTreeRefresh={handleTreeRefresh}
        onKnowledgeRefresh={handleKnowledgeRefresh}
        knowledgeRefreshKey={knowledgeRefreshKey}
        onNavigate={onNavigate}
        activeView={activeView}
        treeNodes={treeNodes}
        selectedNodeId={selectedNodeId}
        onSectionOrderUpdated={() => setSectionOrderVersion((v) => v + 1)}
        onToggleRightPanel={onToggleRightPanel}
        rightPanelCollapsed={rightPanelCollapsed}
      />
      <CenterPanel
        activeView={activeView}
        treeRefreshKey={treeRefreshKey}
        onTreeRefresh={handleTreeRefresh}
        knowledgeRefreshKey={knowledgeRefreshKey}
        onKnowledgeRefresh={handleKnowledgeRefresh}
        resumeData={generatedResumeData}
        templateId={selectedTemplateId}
        onTemplateSelect={handleTemplateSelect}
        onTreeNodesUpdate={handleTreeNodesUpdate}
        onNodeSelect={setSelectedNodeId}
        sectionOrderVersion={sectionOrderVersion}
        structuredJD={structuredJD}
        onExpandRightPanel={() => onToggleRightPanel(false)}
        navKey={navKey}
        agentContext={buildAgentContext}
        pendingAsk={pendingAsk}
        onPendingAskConsumed={() => setPendingAsk(null)}
      />
      {/* 右栏：收起时仅显示一个展开按钮条 */}
      {rightPanelCollapsed ? (
        <button
          onClick={() => onToggleRightPanel(false)}
          className="flex flex-col items-center justify-center bg-bg-secondary border-l border-border-default cursor-pointer hover:bg-bg-hover transition-colors group"
          style={{ width: 32 }}
          title="展开右栏（职位截图分析）"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-text-tertiary group-hover:text-text-primary transition-colors">
            <path d="M2 8h12M8 2l6 6-6 6" />
          </svg>
          <span className="text-[10px] text-text-tertiary group-hover:text-text-primary transition-colors mt-1" style={{ writingMode: 'vertical-rl' }}>
            展开右栏
          </span>
        </button>
      ) : (
        <RightPanel
          resumeData={generatedResumeData}
          onResumeGenerated={handleResumeGenerated}
          templateId={selectedTemplateId}
          treeNodes={treeNodes}
          onJDAnalyzed={setStructuredJD}
          gapReport={gapReport}
          onGapReport={setGapReport}
          onQuickAsk={handleQuickAsk}
          onCollapse={() => onToggleRightPanel(true)}
        />
      )}
    </div>
  );
}
