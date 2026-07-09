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
import TemplateSelector from '@/components/template/TemplateSelector';
import ResumePreview from '@/components/template/ResumePreview';
import DiffView from '@/components/diff/DiffView';
import CompletenessBar from '@/components/completeness/CompletenessBar';
import { getTemplates, getTree, deleteNode, generateFull, regenerateSection, updateSection, getUpstreamChanges, mergeAll, mergeField, rejectField } from '@/lib/api';
import type { UpstreamChanges } from '@/lib/api';
import type { ResumeNode, TreeData } from '@/types/tree';
import type { ActiveView } from '@/types/knowledge';
import type { TemplateInfo } from '@/types/template';

const TAB_PILLS = ['版本树', '编辑器', 'Diff 对比'] as const;

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
  sectionOrderVersion = 0,
  structuredJD = null,
  onExpandRightPanel,
  navKey = 0,
}: CenterPanelProps) {
  const [activeTab, setActiveTab] = useState<string>('版本树');

  // navKey 变化时重置 activeTab 到版本树（每次点击导航项都触发）
  useEffect(() => {
    setActiveTab('版本树');
  }, [navKey]);
  const [selectedNode, setSelectedNode] = useState<ResumeNode | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  // US-17: 上游变更
  const [upstreamChanges, setUpstreamChanges] = useState<UpstreamChanges | null>(null);
  const [showUpstreamPanel, setShowUpstreamPanel] = useState(false);
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

  const handleNodeSelect = useCallback((node: ResumeNode) => {
    setSelectedNode(node);
    onNodeSelect?.(node.node_id);
    setShowUpstreamPanel(false);
  }, [onNodeSelect]);

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

  // US-17: 全部接受合并
  const handleMergeAll = useCallback(async () => {
    if (!selectedNode) return;
    try {
      await mergeAll(selectedNode.node_id);
      setUpstreamChanges(null);
      setShowUpstreamPanel(false);
      // 刷新节点数据
      const data = await getTree();
      setTree(data);
      const updated = data.nodes.find((n) => n.node_id === selectedNode.node_id);
      if (updated) setSelectedNode(updated);
      onTreeNodesUpdate?.(data.nodes);
    } catch {
      // 静默失败
    }
  }, [selectedNode, onTreeNodesUpdate]);

  // US-18: 单字段接受合并
  const handleMergeField = useCallback(async (field: string) => {
    if (!selectedNode) return;
    try {
      await mergeField(selectedNode.node_id, field);
      // 刷新上游变更状态
      const data = await getUpstreamChanges(selectedNode.node_id);
      if (data.has_upstream_update && data.count > 0) {
        setUpstreamChanges(data);
      } else {
        setUpstreamChanges(null);
        setShowUpstreamPanel(false);
        // 刷新树节点状态
        const treeData = await getTree();
        setTree(treeData);
        const updated = treeData.nodes.find((n) => n.node_id === selectedNode.node_id);
        if (updated) setSelectedNode(updated);
        onTreeNodesUpdate?.(treeData.nodes);
      }
    } catch {
      // 静默失败
    }
  }, [selectedNode, onTreeNodesUpdate]);

  // US-18: 单字段拒绝
  const handleRejectField = useCallback(async (field: string) => {
    if (!selectedNode) return;
    try {
      await rejectField(selectedNode.node_id, field);
      // 刷新上游变更状态
      const data = await getUpstreamChanges(selectedNode.node_id);
      if (data.has_upstream_update && data.count > 0) {
        setUpstreamChanges(data);
      } else {
        setUpstreamChanges(null);
        setShowUpstreamPanel(false);
        const treeData = await getTree();
        setTree(treeData);
        const updated = treeData.nodes.find((n) => n.node_id === selectedNode.node_id);
        if (updated) setSelectedNode(updated);
        onTreeNodesUpdate?.(treeData.nodes);
      }
    } catch {
      // 静默失败
    }
  }, [selectedNode, onTreeNodesUpdate]);

  // US-13: section_order 更新后重新拉取选中节点的 content_json
  useEffect(() => {
    if (sectionOrderVersion === 0 || !selectedNode) return;
    getTree().then((data: TreeData) => {
      const updated = data.nodes.find((n) => n.node_id === selectedNode.node_id);
      if (updated) setSelectedNode(updated);
    });
  }, [sectionOrderVersion]);

  // US-14: 一键生成 / 单段重生成
  const [generating, setGenerating] = useState(false);
  const [generatingSection, setGeneratingSection] = useState<string | null>(null);
  const [generateMsg, setGenerateMsg] = useState<string | null>(null);
  // US-15: 完整性检测刷新触发器
  const [completenessRefreshKey, setCompletenessRefreshKey] = useState(0);
  // US-22: 底部"为该岗位动态生成"按钮 → 切换到编辑器 Tab + 触发生成

  const reloadSelectedNode = useCallback(() => {
    if (!selectedNode) return;
    getTree().then((data: TreeData) => {
      const updated = data.nodes.find((n) => n.node_id === selectedNode.node_id);
      if (updated) {
        setSelectedNode(updated);
        setCompletenessRefreshKey((k) => k + 1);
      }
    });
  }, [selectedNode]);

  const handleGenerateFull = useCallback(async () => {
    if (!selectedNode || generating) return;
    if (!structuredJD) {
      setGenerateMsg('请先在右栏上传 JD 招聘信息');
      setTimeout(() => setGenerateMsg(null), 3000);
      return;
    }
    setGenerating(true);
    setGenerateMsg(null);
    try {
      await generateFull(selectedNode.node_id, structuredJD ?? undefined);
      reloadSelectedNode();
      setGenerateMsg('一键生成完成');
    } catch (err: unknown) {
      setGenerateMsg(err instanceof Error ? err.message : '生成失败');
    } finally {
      setGenerating(false);
      setTimeout(() => setGenerateMsg(null), 3000);
    }
  }, [selectedNode, generating, reloadSelectedNode, structuredJD]);

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
      if (!selectedNode || generatingSection) return;
      if (!structuredJD) {
        setGenerateMsg('请先在右栏上传 JD 招聘信息');
        setTimeout(() => setGenerateMsg(null), 3000);
        return;
      }
      setGeneratingSection(section);
      try {
        await regenerateSection(selectedNode.node_id, section, structuredJD ?? undefined);
        reloadSelectedNode();
      } catch {
        // 静默
      } finally {
        setGeneratingSection(null);
      }
    },
    [selectedNode, generatingSection, reloadSelectedNode, structuredJD],
  );

  // US-15: 段落编辑（防抖保存）
  const editDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleEditSection = useCallback(
    (section: string, data: unknown) => {
      if (!selectedNode) return;
      if (editDebounceRef.current) clearTimeout(editDebounceRef.current);
      editDebounceRef.current = setTimeout(async () => {
        try {
          await updateSection(selectedNode.node_id, section, data);
          reloadSelectedNode();
        } catch {
          // 静默
        }
      }, 500);
    },
    [selectedNode, reloadSelectedNode],
  );

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

  const handleDeleteNode = useCallback(() => {
    if (!selectedNode) return;
    if (window.confirm(`确认删除节点 "${selectedNode.title || selectedNode.node_id}" 吗？`)) {
      deleteNode(selectedNode.node_id)
        .then(() => {
          setSelectedNode(null);
          onNodeSelect?.(null);
          onTreeRefresh?.();
        })
        .catch((err) => {
          console.error('删除节点失败:', err);
        });
    }
  }, [selectedNode, onNodeSelect, onTreeRefresh]);

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

  // 预览数据：优先用选中节点的 content_json，否则用 AI 生成的 resumeData
  const previewData: Record<string, unknown> | null = (() => {
    if (selectedNode?.content_json) {
      try {
        const parsed =
          typeof selectedNode.content_json === 'string'
            ? JSON.parse(selectedNode.content_json)
            : selectedNode.content_json;
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          return parsed as Record<string, unknown>;
        }
      } catch {
        // JSON 解析失败，fallback
      }
    }
    return resumeData;
  })();

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
              onClick={() => setActiveTab(pill)}
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

      {/* Tab 内容：版本树 / 编辑器 / Diff 对比 */}
      {activeTab === '编辑器' ? (
        // US-8：编辑器 Tab = 模板选择器 + 工具栏 + 简历预览
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* US-17: 上游变更提示 + 展开面板 */}
          {upstreamChanges?.has_upstream_update && (
            <div className="border-b border-orange-200 bg-orange-50">
              {/* 提示条 */}
              <div className="px-4 py-2 flex items-center gap-2">
                <span className="w-2 h-2 bg-orange-500 rounded-full flex-shrink-0 animate-pulse" />
                <span className="text-xs text-orange-700">
                  上游有 {upstreamChanges.count} 项个人信息变更待合并
                </span>
                <button
                  onClick={() => setShowUpstreamPanel(!showUpstreamPanel)}
                  className="text-xs text-orange-600 hover:underline ml-auto"
                >
                  {showUpstreamPanel ? '收起 ▲' : '查看变更 ▼'}
                </button>
              </div>
              {/* 展开的变更列表 */}
              {showUpstreamPanel && (
                <div className="px-4 pb-3 space-y-2">
                  {Object.entries(upstreamChanges.changes).map(([field, change]) => {
                    const fieldLabel = field === 'contact' ? '联系方式' : field === 'education' ? '教育背景' : field === 'summary' ? '自我评价' : field;
                    const oldVal = change.old;
                    const newVal = change.new;

                    // 对象类型（contact / education）：字段级表格渲染
                    const isObject = (v: unknown) => v !== null && typeof v === 'object';
                    const isObjectDiff = isObject(oldVal) || isObject(newVal);
                    const oldObj = (oldVal && typeof oldVal === 'object' ? oldVal : {}) as Record<string, unknown>;
                    const newObj = (newVal && typeof newVal === 'object' ? newVal : {}) as Record<string, unknown>;
                    const allKeys = Array.from(new Set([...Object.keys(oldObj), ...Object.keys(newObj)]));

                    // 字段名中文映射
                    const fieldNames: Record<string, string> = {
                      name: '姓名', gender: '性别', birth_date: '出生年月', phone: '电话',
                      email: '邮箱', location: '所在城市', website: '个人网站',
                      github: 'GitHub', linkedin: 'LinkedIn',
                      school: '学校', degree: '学历', major: '专业', start_date: '开始', end_date: '结束',
                    };

                    return (
                      <div key={field} className="bg-white rounded-md border border-orange-200 p-2.5 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="text-xs font-medium text-text-primary">{fieldLabel}</div>
                          {/* US-18: 逐字段接受/拒绝按钮 */}
                          <div className="flex gap-1">
                            <button
                              onClick={() => handleMergeField(field)}
                              className="px-2 py-0.5 text-[10px] font-medium text-white bg-green-500 hover:bg-green-600 rounded transition-colors"
                            >
                              接受
                            </button>
                            <button
                              onClick={() => handleRejectField(field)}
                              className="px-2 py-0.5 text-[10px] font-medium text-text-secondary bg-gray-100 hover:bg-gray-200 rounded transition-colors"
                            >
                              拒绝
                            </button>
                          </div>
                        </div>
                        {isObjectDiff ? (
                          <div className="space-y-0.5">
                            {allKeys.map((key) => {
                              const ov = oldObj[key];
                              const nv = newObj[key];
                              const changed = JSON.stringify(ov) !== JSON.stringify(nv);
                              return (
                                <div key={key} className={`flex items-center gap-2 px-2 py-0.5 rounded-sm text-xs ${changed ? 'bg-orange-50' : ''}`}>
                                  <span className="text-text-muted w-16 flex-shrink-0">{fieldNames[key] ?? key}</span>
                                  {changed ? (
                                    <>
                                      <span className="text-error line-through flex-1">{String(ov ?? '')}</span>
                                      <span className="text-text-muted">→</span>
                                      <span className="text-success flex-1">{String(nv ?? '')}</span>
                                    </>
                                  ) : (
                                    <span className="text-text-tertiary flex-1">{String(nv ?? '')}</span>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="flex items-start gap-2">
                            <div className="flex-1">
                              <span className="text-[10px] text-error mr-1">旧:</span>
                              <span className="text-xs text-text-tertiary line-through">{String(oldVal ?? '')}</span>
                            </div>
                            <span className="text-text-muted text-xs">→</span>
                            <div className="flex-1">
                              <span className="text-[10px] text-success mr-1">新:</span>
                              <span className="text-xs text-text-primary">{String(newVal ?? '')}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <button
                    onClick={handleMergeAll}
                    className="w-full py-2 text-xs font-medium text-white bg-orange-500 hover:bg-orange-600 rounded-md transition-colors"
                  >
                    全部接受合并
                  </button>
                </div>
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
          <div className="flex-1 overflow-y-auto p-4 bg-bg-secondary">
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
              onClose={() => setSelectedNode(null)}
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
              onClick={handleDeleteNode}
              disabled={!selectedNode}
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
    </main>
  );
}
