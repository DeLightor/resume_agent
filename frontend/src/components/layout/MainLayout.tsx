// frontend/src/components/layout/MainLayout.tsx
// 三栏 flex 布局容器：左 260px / 中 flex-1 / 右 380px
// 在此层持有 treeRefreshKey 状态，连接左栏上传成功 → 中栏版本树刷新

import { useCallback, useState } from 'react';
import LeftPanel from './LeftPanel';
import CenterPanel from './CenterPanel';
import RightPanel from './RightPanel';

export default function MainLayout() {
  // 上传成功后递增，触发 VersionTree 重新拉取
  const [treeRefreshKey, setTreeRefreshKey] = useState(0);

  const handleTreeRefresh = useCallback(() => {
    setTreeRefreshKey((k) => k + 1);
  }, []);

  return (
    <div
      className="flex overflow-hidden"
      style={{ height: 'calc(100vh - var(--header-height))' }}
    >
      <LeftPanel onTreeRefresh={handleTreeRefresh} />
      <CenterPanel
        treeRefreshKey={treeRefreshKey}
        onTreeRefresh={handleTreeRefresh}
      />
      <RightPanel />
    </div>
  );
}
