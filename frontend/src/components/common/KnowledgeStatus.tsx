// frontend/src/components/common/KnowledgeStatus.tsx
// 知识库状态指示器（切片数 + 索引进度）
// 启动时调用 getKnowledgeStats() 获取真实数据；
// refreshKey 变化时重新拉取（知识素材上传 / 删除后递增）。

import { useEffect, useState } from 'react';
import { getKnowledgeStats } from '@/lib/api';
import type { KnowledgeStats } from '@/types/knowledge';

interface KnowledgeStatusProps {
  /** 变化时触发重新拉取（父层在上传 / 删除后递增） */
  refreshKey?: number;
  /** 后端标识，仅用于展示 */
  backend?: string;
}

/** 默认占位，避免首次加载前显示 0 */
const DEFAULT_STATS: KnowledgeStats = {
  chunk_count: 0,
  document_count: 0,
  indexing_status: 'idle',
};

export default function KnowledgeStatus({
  refreshKey = 0,
  backend = 'Chroma local',
}: KnowledgeStatusProps) {
  const [stats, setStats] = useState<KnowledgeStats>(DEFAULT_STATS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getKnowledgeStats()
      .then((data) => {
        if (!cancelled) {
          setStats(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载知识库状态失败');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // 索引进度：以切片数 / 100 简单估算（0-100），后端若提供 indexing_status
  // 可进一步细化。这里用切片数作为进度代理，上限 100。
  const progress = Math.min(100, Math.round((stats.chunk_count / 100) * 100));

  return (
    <div className="mt-auto p-4 border-t border-border-subtle">
      <div className="flex items-center gap-2 text-xs text-text-tertiary mb-2">
        <svg
          width="12"
          height="12"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          style={{ color: 'var(--color-brand-primary)' }}
        >
          <path d="M8 2l1.5 3H14l-2.5 2 1 3.5L8 8.5 3.5 10.5l1-3.5L2 5h4.5z" />
        </svg>
        <span>知识库索引</span>
        {loading && (
          <span className="ml-auto text-[10px] text-text-muted">加载中...</span>
        )}
        {error && (
          <span
            className="ml-auto text-[10px] text-error truncate max-w-[100px]"
            title={error}
          >
            加载失败
          </span>
        )}
      </div>
      <div className="w-full h-1 bg-bg-elevated rounded-full overflow-hidden mb-2">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${progress}%`,
            background:
              'linear-gradient(90deg, var(--color-brand-primary), var(--color-brand-secondary))',
          }}
        />
      </div>
      <div className="text-xs font-mono text-text-muted tracking-wider">
        {stats.chunk_count} 篇切片 · {stats.document_count} 篇文档 · {backend}
      </div>
    </div>
  );
}
