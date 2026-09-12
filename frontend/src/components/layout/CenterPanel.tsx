// frontend/src/components/layout/CenterPanel.tsx
// 中栏：面包屑 + Tab Pills（版本树/预览/Diff）+ VersionTree 画布
// US-2：联动节点选中、详情浮层、新建节点弹窗、面包屑动态路径
// US-3：支持 activeView 切换（'version-tree' | 'knowledge'），
//       knowledge 模式下渲染 KnowledgeView 替代版本树

import { useCallback, useEffect, useRef, useState } from 'react';
import Breadcrumb from '@/components/common/Breadcrumb';
import VersionTree from '@/components/tree/VersionTree';
import NodeDetailPanel from '@/components/tree/NodeDetailPanel';
import CreateNodeModal from '@/components/tree/CreateNodeModal';
import KnowledgeView from '@/components/knowledge/KnowledgeView';
import AgentWorkbench from '@/components/agent/AgentWorkbench';
import ApplicationTrackerView from '@/components/applications/ApplicationTrackerView';
import ApplicationCreateModal from '@/components/applications/ApplicationCreateModal';
import TemplateSelector from '@/components/template/TemplateSelector';
import ResumePreview from '@/components/template/ResumePreview';
import DiffView from '@/components/diff/DiffView';
import UpstreamReview from '@/components/diff/UpstreamReview';
import CompletenessBar from '@/components/completeness/CompletenessBar';
import { getTemplates, getTree, deleteNode, generateFull, regenerateSection, getNode, moveNodeHistory, getUpstreamChanges, mergeAll, mergeField, rejectField } from '@/lib/api';
import { useNodeDraft, nodeDraftStore } from '@/hooks/useNodeDraft';
import ContentDraftReview from '@/components/diff/ContentDraftReview';
import type { DraftReview } from '@/components/diff/ContentDraftReview';
import { HistoryPanel, TrashPanel } from '@/components/tree/EditProtectionPanels';
import type { UpstreamChanges } from '@/lib/api';
import type { ResumeNode, TreeData } from '@/types/tree';
import type { ActiveView } from '@/types/knowledge';
import type { TemplateInfo } from '@/types/template';

const TAB_PILLS = ['版本树', '编辑器', 'Diff 对比', '回收站'] as const;

/** API 调用失败时的硬编码 fallback 模板 */
const FALLBACK_TEMPLATES: TemplateInfo[] = [
  { id: 'modern', name: '现代简约', description: '简洁现代风，分隔线 + 左对齐标题', theme_color: '#1d4ed8' },
  { id: 'classic', name: '经典色块', description: '色块标题条 + 白字标题，沉稳大气', theme_color: '#1C487C' },
  { id: 'tech', name: '紧凑技术风', description: '页边距小、字号紧凑，适合技术岗', theme_color: '#0F766E' },
  { id: 'minimal', name: '极简白', description: '单栏大量留白，无色块无分隔线', theme_color: '#333333' },
  { id: 'two_column', name: '暖橙卡片风', description: '暖橙色调，段落圆角卡片，活泼有层次', theme_color: '#EA580C' },
  { id: 'academic', name: '学术风', description: '论文格式，衬线字体，居中标题', theme_color: '#1a1a1a' },
];

interface CenterPanelProps {
  /** 中栏当前视图：版本树 / 知识库 */
  activeView?: ActiveView;
  /** 版本树刷新 key，变化时重新拉取 */
  treeRefreshKey?: number;
  /** 触发版本树刷新（新建节点后调用，递增 treeRefreshKey） */
  onTreeRefresh?: () => void;
  /** 知识库刷新 key，变化时重新拉取文档列表 */
  knowledgeRefreshKey?: number;
  /** 触发知识库刷新（删除后递增 knowledgeRefreshKey） */
  onKnowledgeRefresh?: () => void;
  /** US-8：AI 生成的简历数据，用于编辑器 Tab 预览 */
  resumeData?: Record<string, unknown> | null;
  /** US-8：当前选中的模板 id */
  templateId?: string;
  /** US-8：切换模板回调 */
  onTemplateSelect?: (id: string) => void;
  /** US-10：树数据加载后回灌节点列表给 MainLayout（供 Diff 选择器和保存功能使用） */
  onTreeNodesUpdate?: (nodes: ResumeNode[]) => void;
  /** US-12：选中节点变化时通知 MainLayout（传给左栏 PersonalInfoForm） */
  onNodeSelect?: (nodeId: string | null) => void;
  /** US-13：section_order 更新版本号，变化时重新拉取选中节点数据 */
  sectionOrderVersion?: number;
  /** US-14: JD 结构化数据（从右栏 JD 分析获取），用于一键生成 */
  structuredJD?: Record<string, unknown> | null;
  /** 展开右栏回调（点击"为该岗位动态生成"时展开右栏） */
  onExpandRightPanel?: () => void;
  /** 导航计数器：每次点击导航递增，强制重置 activeTab 到"版本树" */
  navKey?: number;
  /** US-29：工作台上下文提供者（透传给 AgentWorkbench，send 时携带） */
  agentContext?: () => Record<string, unknown>;
  /** US-29：待自动发送的快捷指令（右栏入口触发） */
  pendingAsk?: import('./MainLayout').PendingAsk | null;
  /** US-29：快捷指令已被 AgentWorkbench 消费（清除 MainLayout 状态） */
  onPendingAskConsumed?: () => void;
}

/**
 * 从选中节点回溯 parent_id 链生成路径。
 * 未选中或无树数据时返回 ['master']。
 */
function computePath(tree: TreeData | null, node: ResumeNode | null): string[] {
  if (!tree || !node) return ['master'];
  const path: string[] = [];
  let current: ResumeNode | null = node;
  while (current) {
    const cur: ResumeNode = current;
    path.unshift(cur.node_type === 'master' ? cur.node_id : (cur.title || cur.node_id));
    const parent = tree.nodes.find((n) => n.node_id === cur.parent_id);
    current = parent ?? null;
  }
  if (path.length === 0 || path[0] !== 'master') path.unshift('master');
  return path;
}

export default function CenterPanel({
  activeView = 'version-tree',
  treeRefreshKey,
  onTreeRefresh,
  knowledgeRefreshKey,
  onKnowledgeRefresh,
  resumeData = null,
  templateId = 'modern',
  onTemplateSelect,
  onTreeNodesUpdate,
  onNodeSelect,
  structuredJD = null,
  onExpandRightPanel,
  navKey = 0,
  agentContext,
  pendingAsk = null,
  onPendingAskConsumed,
}: CenterPanelProps) {
  const [activeTab, setActiveTab] = useState<string>('版本树');

  // navKey 变化时重置 activeTab 到版本树（每次点击导航项都触发）
  useEffect(() => {
    setActiveTab('版本树');
  }, [navKey]);
  const [selectedNode, setSelectedNode] = useState<ResumeNode | null>(null);
  const draft = useNodeDraft(selectedNode);
  const [actionError, setActionError] = useState('');
  const [draftReview, setDraftReview] = useState<DraftReview | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showApplicationCreate, setShowApplicationCreate] = useState(false);
  const selectedId = useRef<string | null>(null);
  selectedId.current = selectedNode?.node_id ?? null;
  const applySavedNode = useCallback((node: ResumeNode) => {
    if (selectedId.current === node.node_id) setSelectedNode(node);
    onTreeRefresh?.();
  }, [onTreeRefresh]);
  useEffect(() => {
    const saved = (event: Event) => {
      const node = (event as CustomEvent<ResumeNode>).detail;
      if (selectedId.current === node.node_id) setSelectedNode(node);
    };
    window.addEventListener('node-draft-saved', saved);
    return () => window.removeEventListener('node-draft-saved', saved);
  }, []);
  useEffect(() => { void draft.flush(); }, [activeView, navKey]);
  useEffect(() => {
    const undo = async (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'z' || event.altKey || target.closest('input, textarea, select, [contenteditable="true"], dialog')) return;
      if (!selectedNode || activeView !== 'version-tree') return;
      event.preventDefault();
      if (!await draft.flush()) return;
      try {
        const id = selectedNode.node_id;
        applySavedNode(await moveNodeHistory(id, event.shiftKey ? 'redo' : 'undo', nodeDraftStore.get(id).version));
      } catch (error) { setActionError(error instanceof Error ? error.message : '撤销失败'); }
    };
    window.addEventListener('keydown', undo);
    return () => window.removeEventListener('keydown', undo);
  }, [selectedNode, activeView, draft.flush, applySavedNode]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  // US-17: 上游变更
  const [upstreamChanges, setUpstreamChanges] = useState<UpstreamChanges | null>(null);
  const [showUpstreamPanel, setShowUpstreamPanel] = useState(false);
  const [upstreamBusy, setUpstreamBusy] = useState(false);
  // 树数据由 VersionTree onTreeLoad 回灌，用于路径回溯与新建节点父选项
  const [tree, setTree] = useState<TreeData | null>(null);
  // US-8：模板列表（从 API 获取，失败时用 fallback）
  const [templates, setTemplates] = useState<TemplateInfo[]>(FALLBACK_TEMPLATES);

  // 拉取模板列表，失败时回退到硬编码列表
  useEffect(() => {
    let cancelled = false;
    getTemplates()
      .then((list) => {
        if (!cancelled && list.length > 0) {
          setTemplates(list);
        }
      })
      .catch(() => {
        // 静默回退到 fallback 模板
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleNodeSelect = useCallback(async (node: ResumeNode) => {
    if (!await draft.flush()) return;
    setSelectedNode(node);
    onNodeSelect?.(node.node_id);
    setShowUpstreamPanel(false);
  }, [onNodeSelect, draft.flush]);

  // US-17: 选中节点时拉取上游变更状态
  useEffect(() => {
    if (!selectedNode?.has_upstream_update) {
      setUpstreamChanges(null);
      return;
    }
    let cancelled = false;
    getUpstreamChanges(selectedNode.node_id)
      .then((data) => {
        if (!cancelled) setUpstreamChanges(data);
      })
      .catch(() => {
        if (!cancelled) setUpstreamChanges(null);
      });
    return () => { cancelled = true; };
  }, [selectedNode]);

  // US-33: this is an invalidation signal, not a content transport.  The
  // draft store keeps a dirty editor intact and marks a genuine server race.
  useEffect(() => {
    const stream = new EventSource('/api/tree/events');
    stream.addEventListener('tree_update', () => {
      void getTree().then((data) => {
        setTree(data);
        onTreeNodesUpdate?.(data.nodes);
        const id = selectedId.current;
        if (!id) return;
        return getNode(id).then((node) => {
          if (selectedId.current !== id) return;
          nodeDraftStore.receive(node);
          setSelectedNode(node);
        });
      }).catch(() => { /* EventSource reconnects; the next signal retries. */ });
    });
    return () => stream.close();
  }, [onTreeNodesUpdate]);

  const refreshUpstream = useCallback(async (nodeId: string) => {
    const [snapshot, treeData, refreshed] = await Promise.all([getUpstreamChanges(nodeId), getTree(), getNode(nodeId)]);
    if (selectedId.current !== nodeId) return;
    setUpstreamChanges(snapshot.has_upstream_update && snapshot.count ? snapshot : null);
    if (!snapshot.has_upstream_update || !snapshot.count) setShowUpstreamPanel(false);
    setTree(treeData);
    onTreeNodesUpdate?.(treeData.nodes);
    nodeDraftStore.receive(refreshed);
    setSelectedNode(refreshed);
  }, [onTreeNodesUpdate]);

  const handleUpstreamAction = useCallback(async (action: 'accept' | 'retain' | 'all', field?: string) => {
    if (!selectedNode || !upstreamChanges || upstreamChanges.upstream_version === null || !await draft.flush()) return;
    const nodeId = selectedNode.node_id;
    try {
      setUpstreamBusy(true);
      const version = nodeDraftStore.get(nodeId).version;
      if (action === 'all') await mergeAll(nodeId, version, upstreamChanges.upstream_version);
      else if (action === 'accept' && field) await mergeField(nodeId, field, version, upstreamChanges.upstream_version);
      else if (action === 'retain' && field) await rejectField(nodeId, field, version, upstreamChanges.upstream_version);
      await refreshUpstream(nodeId);
    } catch (error) {
      const stale = error instanceof Error && /节点已更新|上游内容已更新|409/.test(error.message);
      setActionError(stale ? '内容已更新，已刷新变更，请重新选择。' : error instanceof Error ? error.message : '合并失败，请刷新后重试');
      if (stale) void refreshUpstream(nodeId);
    } finally {
      setUpstreamBusy(false);
    }
  }, [selectedNode, upstreamChanges, draft.flush, refreshUpstream]);

  // US-14: 一键生成 / 单段重生成
  const generationLock = useRef(false);
  const [generating, setGenerating] = useState(false);
  const [generatingSection, setGeneratingSection] = useState<string | null>(null);
  const [generateMsg, setGenerateMsg] = useState<string | null>(null);
  // US-15: 完整性检测刷新触发器
  const [completenessRefreshKey, setCompletenessRefreshKey] = useState(0);
  // US-22: 底部"为该岗位动态生成"按钮 → 切换到编辑器 Tab + 触发生成

  const handleGenerateFull = useCallback(async () => {
    if (!selectedNode || generationLock.current) return;
    if (!structuredJD) {
      setGenerateMsg('请先在右栏上传 JD 招聘信息');
      setTimeout(() => setGenerateMsg(null), 3000);
      return;
    }
    generationLock.current = true;
    setGenerating(true);
    setGenerateMsg(null);
    try {
      if (!await draft.flush()) return;
      const base = await getNode(selectedNode.node_id);
      const result = await generateFull(base.node_id, structuredJD ?? undefined);
      setDraftReview({ node: { ...base, content_json: result.base_content as Record<string, unknown> }, content: result.content as Record<string, unknown>, baseVersion: Number(result.base_version) });
      setGenerateMsg('生成完成，请审阅草稿');
    } catch (err: unknown) {
      setGenerateMsg(err instanceof Error ? err.message : '生成失败');
    } finally {
      generationLock.current = false;
      setGenerating(false);
      setTimeout(() => setGenerateMsg(null), 3000);
    }
  }, [selectedNode, generating, draft.flush, structuredJD]);

  // US-22: 底部"为该岗位动态生成"按钮 → 切换到编辑器 Tab + 触发生成
  const handleBottomGenerate = useCallback(async () => {
    // 无论什么情况，先切换到编辑器 Tab
    setActiveTab('编辑器');

    if (!selectedNode) {
      setGenerateMsg('请先在版本树中选中一个分支节点');
      setTimeout(() => setGenerateMsg(null), 4000);
      return;
    }
    if (!structuredJD) {
      // 没有 JD → 展开右栏让用户上传
      onExpandRightPanel?.();
      setGenerateMsg('请先在右栏上传岗位截图，分析完成后将自动生成简历');
      setTimeout(() => setGenerateMsg(null), 4000);
      return;
    }
    // 有 JD → 直接开始生成
    handleGenerateFull();
  }, [selectedNode, structuredJD, handleGenerateFull, onExpandRightPanel]);

  const handleRegenerateSection = useCallback(
    async (section: string) => {
      if (!selectedNode || generationLock.current) return;
      if (!structuredJD) {
        setGenerateMsg('请先在右栏上传 JD 招聘信息');
        setTimeout(() => setGenerateMsg(null), 3000);
        return;
      }
      generationLock.current = true;
      setGeneratingSection(section);
      try {
        if (!await draft.flush()) return;
        const base = await getNode(selectedNode.node_id);
        const result = await regenerateSection(base.node_id, section, structuredJD ?? undefined);
        setDraftReview({ node: { ...base, content_json: result.base_content as Record<string, unknown> }, content: result.content as Record<string, unknown>, baseVersion: Number(result.base_version) });
      } catch (error) {
        setActionError(error instanceof Error ? error.message : '生成失败');
      } finally {
        generationLock.current = false;
        setGeneratingSection(null);
      }
    },
    [selectedNode, generatingSection, draft.flush, structuredJD],
  );

  const handleEditSection = useCallback((section: string, data: unknown) => {
    draft.edit(content => { content[section] = data; });
  }, [draft.edit]);

  const handleTreeLoad = useCallback((data: TreeData) => {
    setTree(data);
    onTreeNodesUpdate?.(data.nodes);
  }, [onTreeNodesUpdate]);

  const handleCreated = useCallback(() => {
    setShowCreateModal(false);
    onTreeRefresh?.();
  }, [onTreeRefresh]);

  const handleTemplateSelect = useCallback(
    (id: string) => {
      onTemplateSelect?.(id);
    },
    [onTemplateSelect],
  );

  const handleDeleteNode = useCallback(async () => {
    if (!selectedNode || !await draft.flush()) return;
    if (window.confirm(`确认删除节点 "${selectedNode.title || selectedNode.node_id}" 及其子节点移入回收站吗？30 天内可恢复。`)) {
      deleteNode(selectedNode.node_id)
        .then(() => {
          setSelectedNode(null);
          onNodeSelect?.(null);
          onTreeRefresh?.();
        })
        .catch((err) => {
          setActionError(err instanceof Error ? err.message : '删除失败');
        });
    }
  }, [selectedNode, onNodeSelect, onTreeRefresh, draft.flush]);

  // 知识库视图：渲染 KnowledgeView，不显示版本树 Tab / 面包屑
  if (activeView === 'knowledge') {
    return (
      <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
        <KnowledgeView
          refreshKey={knowledgeRefreshKey}
          onKnowledgeRefresh={onKnowledgeRefresh}
        />
      </main>
    );
  }

  if (activeView === 'applications') {
    return <ApplicationTrackerView />;
  }

  // AI 助手视图（US-28）：渲染 AgentWorkbench（对话 + 行为时间线）
  // US-29：透传工作台上下文与快捷指令（pendingAsk 自动发送）
  if (activeView === 'agent') {
    return (
      <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
        <AgentWorkbench
          agentContext={agentContext}
          pendingAsk={pendingAsk}
          onPendingAskConsumed={onPendingAskConsumed}
        />
      </main>
    );
  }

  // 预览数据：优先用选中节点的 content_json，否则用 AI 生成的 resumeData
  const previewData = draft.content ?? resumeData;

  const breadcrumbPath = computePath(tree, selectedNode);

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
      {/* Breadcrumb + Tab pills */}
      <div className="flex items-center px-5 py-3 gap-2 border-b border-border-subtle text-sm">
        <Breadcrumb path={breadcrumbPath} />
        <div className="ml-auto flex gap-0.5 bg-bg-tertiary rounded-md p-0.5">
          {TAB_PILLS.map((pill) => (
            <button
              key={pill}
              onClick={async () => { if (await draft.flush()) setActiveTab(pill); }}
              className={`px-4 py-1 rounded-sm text-xs transition-all border-none cursor-pointer font-body ${
                activeTab === pill
                  ? 'bg-bg-elevated text-text-primary font-medium shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              {pill}
            </button>
          ))}
        </div>
      </div>

      {selectedNode && <div className="flex flex-wrap gap-3 items-center px-4 py-2 border-b border-border-subtle text-xs" onCompositionStart={() => draft.setComposing(true)} onCompositionEnd={() => draft.setComposing(false)}>
        <span role="status">{{idle: '已同步', pending: '待保存…', saving: '保存中…', saved: '已保存', error: '保存失败', conflict: '版本冲突'}[draft.status]}</span>
        <button onClick={() => setShowHistory(v => !v)}>编辑历史 / 撤销</button>
        {draft.error && <><span role="alert" className="text-error">{draft.error}</span><button onClick={() => void draft.flush()}>重试保存</button><button onClick={() => { if (window.confirm('放弃本地未保存内容并加载服务器版本？')) void draft.reload(); }}>放弃本地草稿并刷新</button></>}
      </div>}
      {actionError && <div role="alert" className="text-error text-sm px-4 py-2">{actionError}<button className="ml-3" onClick={() => setActionError('')}>关闭</button></div>}
      {showHistory && selectedNode && <HistoryPanel node={selectedNode} beforeAction={draft.flush} onChanged={applySavedNode} />}
      {draftReview && <ContentDraftReview draft={draftReview} onClose={() => setDraftReview(null)} onApplied={node => { nodeDraftStore.receive(node); applySavedNode(node); setDraftReview(null); setCompletenessRefreshKey(k => k + 1); }} />}
      {/* Tab 内容：版本树 / 编辑器 / Diff 对比 */}
      {activeTab === '回收站' ? <TrashPanel onChanged={() => onTreeRefresh?.()} /> : activeTab === '编辑器' ? (
        // US-8：编辑器 Tab = 模板选择器 + 工具栏 + 简历预览
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* US-33: 内容级上游变更提示 + 展开审阅 */}
          {upstreamChanges?.has_upstream_update && (
            <div className="border-b border-orange-200 bg-orange-50">
              <div className="px-4 py-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-orange-500 rounded-full flex-shrink-0 animate-pulse" />
                <span className="text-xs text-orange-700">
                  上游有 {upstreamChanges.count} 项内容变更待审阅
                </span>
                <button
                  onClick={() => setShowUpstreamPanel(!showUpstreamPanel)}
                  className="text-xs text-orange-600 hover:underline ml-auto"
                >
                  {showUpstreamPanel ? '收起 ▲' : '查看变更 ▼'}
                </button>
              </div>
              {showUpstreamPanel && (
                <UpstreamReview snapshot={upstreamChanges} source={upstreamChanges.source_node_id ?? '上游节点'} busy={upstreamBusy} stale={draft.status === 'conflict'} onRefresh={() => { if (selectedNode) void refreshUpstream(selectedNode.node_id); }} onAction={(action, field) => void handleUpstreamAction(action, field)} />
              )}
            </div>
          )}
          <div className="p-3 border-b border-border-subtle">
            <TemplateSelector
              templates={templates}
              selectedId={templateId}
              onSelect={handleTemplateSelect}
            />
          </div>
          {/* US-14: 一键生成工具栏 */}
          <div className="flex items-center gap-2 px-4 py-2 border-b border-border-subtle bg-bg-tertiary">
            <button
              onClick={handleGenerateFull}
              disabled={!selectedNode || generating}
              className="flex items-center gap-1.5 px-3 py-1 rounded-md bg-brand-primary text-white text-xs font-medium hover:bg-brand-primary-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {generating ? (
                <>
                  <svg className="animate-spin w-3 h-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
                  </svg>
                  生成中...
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M8 1v14M1 8h14" />
                  </svg>
                  一键生成
                </>
              )}
            </button>
            {generateMsg && (
              <span className="text-xs text-text-muted">{generateMsg}</span>
            )}
            {!selectedNode && (
              <span className="text-xs text-text-muted">请先选择版本树节点</span>
            )}
            {selectedNode && !structuredJD && !generateMsg && (
              <span className="text-xs text-text-muted">需先在右栏上传 JD 招聘信息</span>
            )}
          </div>
          {/* US-15: 完整性检测条 */}
          <CompletenessBar
            nodeId={selectedNode?.node_id ?? null}
            refreshKey={completenessRefreshKey}
          />
          <div className="flex-1 overflow-y-auto p-4 bg-bg-secondary" onCompositionStart={() => draft.setComposing(true)} onCompositionEnd={() => draft.setComposing(false)}>
            <ResumePreview
              resumeData={previewData}
              templateId={templateId}
              onRegenerateSection={handleRegenerateSection}
              generatingSection={generatingSection}
              onEditSection={handleEditSection}
            />
          </div>
        </div>
      ) : activeTab === 'Diff 对比' ? (
        // US-10：版本 Diff 对比视图
        <div className="flex-1 overflow-y-auto p-4">
          <DiffView nodes={tree?.nodes ?? []} />
        </div>
      ) : (
        <>
          {/* Version tree canvas */}
          <div className="flex-1 relative overflow-hidden">
            <VersionTree
              refreshKey={treeRefreshKey}
              onNodeSelect={handleNodeSelect}
              onTreeLoad={handleTreeLoad}
            />
            <NodeDetailPanel
              node={selectedNode}
              onClose={async () => { if (await draft.flush()) { setSelectedNode(null); onNodeSelect?.(null); } }}
            />
          </div>

          {/* Canvas toolbar */}
          <div className="flex items-center gap-3 px-5 py-3 border-t border-border-subtle border-b border-border-subtle">
            <button
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-transparent text-text-secondary text-sm font-medium border border-border-default rounded-md cursor-pointer transition-all font-body hover:border-border-strong hover:text-text-primary hover:bg-bg-hover"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path d="M8 3v10M3 8h10" />
              </svg>
              新建分支
            </button>
            <button
              onClick={handleBottomGenerate}
              disabled={generating}
              className="inline-flex items-center gap-2 px-5 py-2 text-white text-sm font-medium border-none rounded-md cursor-pointer font-body transition-all hover:brightness-110 hover:-translate-y-px disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
              style={{
                background:
                  'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
                boxShadow: 'var(--shadow-glow-primary)',
              }}
            >
              {generating ? (
                <svg className="animate-spin" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M8 1a7 7 0 1 0 7 7" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 1.5l1.7 3.5 3.8.6-2.8 2.7.7 3.8L8 10.1 4.6 12.1l.7-3.8L2.5 5.6l3.8-.6z" />
                </svg>
              )}
              {generating ? '生成中...' : '为该岗位动态生成'}
            </button>
            <button
              onClick={() => setActiveTab('Diff 对比')}
              className="inline-flex items-center gap-2 px-5 py-2 bg-transparent text-text-secondary text-sm font-medium border border-border-default rounded-md cursor-pointer transition-all font-body hover:border-border-strong hover:text-text-primary hover:bg-bg-hover"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path d="M2 4h12M2 8h8M2 12h10" />
              </svg>
              版本对比 Diff
            </button>
            <button
              onClick={() => setShowApplicationCreate(true)}
              disabled={!selectedNode}
              className="inline-flex items-center gap-2 px-5 py-2 bg-transparent text-text-secondary text-sm font-medium border border-border-default rounded-md cursor-pointer transition-all font-body hover:border-border-strong hover:text-text-primary hover:bg-bg-hover disabled:opacity-50 disabled:cursor-not-allowed"
            >
              记录投递
            </button>
            <button
              onClick={handleDeleteNode}
              disabled={!selectedNode || selectedNode.node_type === 'master'}
              className="inline-flex items-center gap-2 px-5 py-2 bg-transparent text-text-secondary text-sm font-medium border border-border-default rounded-md cursor-pointer transition-all font-body hover:border-border-strong hover:text-text-primary hover:bg-bg-hover disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <path d="M3 4h10M5 4V2h6v2M5 4l1 10h4l1-10" />
              </svg>
              删除节点
            </button>
            {/* US-8：模板选择已移至"编辑器"Tab，此处不再重复展示 */}
          </div>

        </>
      )}

      {/* 新建节点弹窗 */}
      <CreateNodeModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={handleCreated}
        parentOptions={tree?.nodes ?? []}
      />
      {showApplicationCreate && selectedNode && <ApplicationCreateModal
        node={selectedNode}
        structuredJD={structuredJD}
        onClose={() => setShowApplicationCreate(false)}
        onCreated={() => { setShowApplicationCreate(false); setActionError('已创建投递记录，可在“投递追踪”查看。'); }}
      />}
    </main>
  );
}
