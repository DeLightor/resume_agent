// frontend/src/components/layout/MainLayout.tsx
// 三栏 flex 布局容器：左 260px / 中 flex-1 / 右 380px
// 在此层持有 treeRefreshKey / knowledgeRefreshKey / activeView 状态：
// - treeRefreshKey：简历上传成功 → 中栏版本树刷新
// - knowledgeRefreshKey：知识素材上传 / 文档删除 → KnowledgeStatus + KnowledgeView 刷新
// - activeView：左栏导航切换中栏视图（版本树 / 知识库）

import { useCallback, useState } from 'react';
import LeftPanel from './LeftPanel';
import CenterPanel from './CenterPanel';
import RightPanel from './RightPanel';
import type { ActiveView } from '@/types/knowledge';
import type { ResumeNode } from '@/types/tree';

export default function MainLayout() {
  // 上传成功后递增，触发 VersionTree 重新拉取
  const [treeRefreshKey, setTreeRefreshKey] = useState(0);
  // 知识库上传 / 删除后递增，触发 KnowledgeStatus + KnowledgeView 刷新
  const [knowledgeRefreshKey, setKnowledgeRefreshKey] = useState(0);
  // 中栏当前视图
  const [activeView, setActiveView] = useState<ActiveView>('version-tree');
  // US-8：AI 生成的简历数据（右栏 GenerateView 产出 → 中栏 ResumePreview 展示）
  const [generatedResumeData, setGeneratedResumeData] = useState<
    Record<string, unknown> | null
  >(null);
  // US-8：当前选中的模板 id（默认 modern）
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('modern');
  // 版本树节点列表（供 Diff 选择器和保存功能使用）
  const [treeNodes, setTreeNodes] = useState<ResumeNode[]>([]);
  // US-12：当前选中的节点 ID（传给左栏 PersonalInfoForm）
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const handleTreeRefresh = useCallback(() => {
    setTreeRefreshKey((k) => k + 1);
  }, []);

  const handleKnowledgeRefresh = useCallback(() => {
    setKnowledgeRefreshKey((k) => k + 1);
  }, []);

  const handleNavigate = useCallback((view: ActiveView) => {
    setActiveView(view);
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

  return (
    <div
      className="flex overflow-hidden"
      style={{ height: 'calc(100vh - var(--header-height))' }}
    >
      <LeftPanel
        onTreeRefresh={handleTreeRefresh}
        onKnowledgeRefresh={handleKnowledgeRefresh}
        knowledgeRefreshKey={knowledgeRefreshKey}
        onNavigate={handleNavigate}
        selectedNodeId={selectedNodeId}
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
      />
      {/* 右栏始终可见：JD 截图分析 / Gap 报告 / AI 导师均在此栏，
          无需随导航项切换（"职位截图分析"等导航仅影响中栏视图） */}
      <RightPanel
        resumeData={generatedResumeData}
        onResumeGenerated={handleResumeGenerated}
        templateId={selectedTemplateId}
        treeNodes={treeNodes}
      />
    </div>
  );
}
