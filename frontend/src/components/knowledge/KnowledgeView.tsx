// frontend/src/components/knowledge/KnowledgeView.tsx
// 知识库管理视图（US-3）
// - 顶部：语义检索框（输入关键词 → searchKnowledge → 展示结果）
// - 中部：文档列表（文件名 / 类型 badge / 状态 / 创建时间 / 删除按钮）
// - 检索结果区：匹配文本片段（高亮）+ 来源文件 + 相似度分数

import { useCallback, useEffect, useState } from 'react';
import {
  deleteKnowledgeDocument,
  getKnowledgeDocuments,
  getResumeList,
  searchKnowledge,
  deleteResume,
} from '@/lib/api';
import type { ResumeListItem } from '@/types/resume';
import type {
  KnowledgeDocument,
  KnowledgeParseStatus,
  SearchResult,
} from '@/types/knowledge';
import MaterialMiningDrawer from '@/components/knowledge/MaterialMiningDrawer';

interface KnowledgeViewProps {
  /** 变化时重新拉取文档列表（上传 / 删除后递增） */
  refreshKey?: number;
  /** 删除成功后触发，用于刷新 KnowledgeStatus 等外部状态 */
  onKnowledgeRefresh?: () => void;
}

/** 解析状态 → 展示标签 + 颜色 */
const STATUS_META: Record<
  KnowledgeParseStatus,
  { label: string; cls: string }
> = {
  pending: { label: '待处理', cls: 'bg-bg-tertiary text-text-tertiary' },
  parsing: { label: '解析中', cls: 'bg-brand-primary-muted text-brand-primary' },
  success: { label: '已完成', cls: 'bg-[rgba(5,150,105,0.08)] text-success' },
  failed: { label: '失败', cls: 'bg-[rgba(220,38,38,0.08)] text-error' },
  needs_review: { label: '待复核', cls: 'bg-[rgba(217,119,6,0.08)] text-warning' },
};

/** ISO 时间字符串 → 本地化短日期 */
function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** 从文件名推断展示用的类型缩写（大写） */
function typeBadge(fileType: string): string {
  const t = fileType.toLowerCase().replace(/^\./, '');
  if (!t) return 'FILE';
  return t.length <= 4 ? t.toUpperCase() : t.slice(0, 4).toUpperCase();
}

/**
 * 将文本中匹配 query 的片段高亮（大小写不敏感）。
 * 返回 React 节点数组，匹配片段用 <mark> 包裹。
 */
function highlightMatch(text: string, query: string): React.ReactNode {
  const q = query.trim();
  if (!q) return text;
  // 转义正则特殊字符
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(${escaped})`, 'gi');
  // split 携带捕获组 → 结果数组交替为 [非匹配, 匹配, 非匹配, 匹配, ...]
  const parts = text.split(re);
  const qLower = q.toLowerCase();
  return parts.map((part, i) =>
    part.toLowerCase() === qLower ? (
      <mark
        key={i}
        className="bg-brand-primary-muted text-brand-primary rounded-sm px-0.5"
      >
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export default function KnowledgeView({
  refreshKey = 0,
  onKnowledgeRefresh,
}: KnowledgeViewProps) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [resumes, setResumes] = useState<ResumeListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 检索状态
  const [searchQuery, setSearchQuery] = useState('');
  const [activeQuery, setActiveQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // 删除状态
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // 素材挖掘抽屉状态 (US-36)
  const [miningDrawerOpen, setMiningDrawerOpen] = useState(false);

  /** 拉取文档列表 */
  const fetchDocuments = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([getKnowledgeDocuments(), getResumeList()])
      .then(([data, resumeData]) => {
        setDocuments(data);
        setResumes(
          resumeData.filter(
            (item) =>
              item.parse_status === 'success' &&
              item.direction !== 'chat_mining' &&
              (!item.file_path || item.file_path.startsWith('resumes/')),
          ),
        );
        setLoading(false);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载文档列表失败');
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments, refreshKey]);

  /** 执行检索 */
  const handleSearch = useCallback(async () => {
    const q = searchQuery.trim();
    if (!q || searching) return;
    setSearching(true);
    setSearchError(null);
    setActiveQuery(q);
    try {
      const res = await searchKnowledge(q, 5);
      setResults(res.results);
    } catch (err: unknown) {
      setSearchError(err instanceof Error ? err.message : '检索失败');
      setResults([]);
    } finally {
      setSearching(false);
    }
  }, [searchQuery, searching]);

  /** 回车触发检索 */
  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void handleSearch();
    }
  };

  /** 删除文档 */
  const handleDelete = useCallback(
    async (doc: KnowledgeDocument) => {
      if (deletingId) return;
      setDeletingId(doc.id);
      try {
        await deleteKnowledgeDocument(doc.id);
        setDocuments((prev) => prev.filter((d) => d.id !== doc.id));
        onKnowledgeRefresh?.();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : '删除文档失败');
      } finally {
        setDeletingId(null);
      }
    },
    [deletingId, onKnowledgeRefresh],
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
      {/* 顶部：标题 + 检索框 */}
      <div className="flex items-center px-5 py-3 gap-3 border-b border-border-subtle">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{ color: 'var(--color-brand-primary)' }}
          >
            <path d="M8 2l1.5 3H14l-2.5 2 1 3.5L8 8.5 3.5 10.5l1-3.5L2 5h4.5z" />
          </svg>
          个人知识库
        </div>
        <div className="ml-auto flex items-center gap-2 flex-1 max-w-md">
          <div className="relative flex-1">
            <svg
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
              width="14"
              height="14"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <circle cx="7" cy="7" r="5" />
              <path d="M11 11l3 3" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="输入关键词检索知识库..."
              className="w-full pl-8 pr-3 py-1.5 text-sm bg-bg-tertiary border border-border-default rounded-md text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand-primary transition-colors font-body"
            />
          </div>
          <button
            type="button"
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="px-4 py-1.5 text-sm text-white border-none rounded-md cursor-pointer transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed font-body font-medium"
            style={{
              background:
                'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
            }}
          >
            {searching ? '检索中...' : '检索'}
          </button>
        </div>
      </div>

      {/* 主体内容区（可滚动） */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
        {/* 应届生追问式冷启动引导横幅 (US-36) */}
        <div className="rounded-xl p-4 border border-brand-primary/30 bg-gradient-to-r from-brand-primary/10 via-brand-primary-muted/20 to-transparent flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-lg bg-brand-primary/20 text-brand-primary flex items-center justify-center text-lg flex-shrink-0">
              💡
            </div>
            <div>
              <div className="flex items-center gap-2 font-semibold text-text-primary text-sm">
                零经历不知道简历写什么？师兄帮你深挖素材
                <span className="text-[11px] px-2 py-0.5 rounded-full font-medium bg-brand-primary text-white">
                  STAR 向导
                </span>
              </div>
              <p className="text-xs text-text-secondary mt-1 max-w-xl leading-relaxed">
                没有大厂实习也无需焦虑！基于 STAR 黄金法则，将课程大作业、技术竞赛、科研实验或社团统筹经历提炼为高质量简历要点，一键沉淀入个人知识库。
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setMiningDrawerOpen(true)}
            className="px-4 py-2 rounded-lg text-xs font-semibold text-white shadow transition-all hover:brightness-110 flex-shrink-0 cursor-pointer border-none flex items-center gap-1.5"
            style={{
              background:
                'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
            }}
          >
            <span>🚀</span> 开启经历挖掘
          </button>
        </div>

        {/* 已确认的简历区 */}
        <div>
          <div className="mb-3 text-sm font-semibold text-text-primary">
            已确认的简历
            <span className="ml-2 text-xs font-normal text-text-tertiary">· 共 {resumes.length} 份</span>
          </div>
          {resumes.length === 0 ? (
            <div className="rounded-md border border-dashed border-border-default p-4 text-sm text-text-muted">暂无已确认简历</div>
          ) : (
            <div className="flex flex-col gap-1">
              {resumes.map((resume) => (
                <div key={resume.id} className="flex items-center gap-3 rounded-md border border-border-subtle bg-bg-secondary px-3 py-2.5">
                  <span className="min-w-[36px] rounded bg-bg-tertiary px-1.5 py-0.5 text-center font-mono text-[10px] text-text-secondary">简历</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-text-primary" title={resume.file_name}>{resume.file_name}</span>
                  <span className="text-xs text-brand-primary">{resume.direction || '未指定方向'}</span>
                  <span className="hidden text-xs text-text-muted sm:block">{formatDate(resume.created_at)}</span>
                  <button type="button" className="min-h-8 px-2 text-xs text-error" onClick={async () => { if (window.confirm('删除这份已入库简历？')) { await deleteResume(resume.id); fetchDocuments(); onKnowledgeRefresh?.(); } }}>删除</button>
                </div>
              ))}
            </div>
          )}
        </div>
        {/* 检索错误提示 */}
        {searchError && (
          <div className="mb-4 text-xs text-error bg-[rgba(220,38,38,0.05)] border border-[rgba(220,38,38,0.15)] rounded-md px-3 py-2">
            检索失败：{searchError}
          </div>
        )}

        {/* 检索结果区 */}
        {(results.length > 0 || searching) && (
          <section className="mb-6">
            <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-text-primary">
              <svg
                className="w-4 h-4 opacity-70"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                style={{ color: 'var(--color-brand-primary)' }}
              >
                <circle cx="7" cy="7" r="5" />
                <path d="M11 11l3 3" />
              </svg>
              检索结果
              {activeQuery && (
                <span className="text-text-tertiary font-normal text-xs">
                  · “{activeQuery}” · {searching ? '...' : `${results.length} 条命中`}
                </span>
              )}
            </div>

            {searching ? (
              <div className="text-sm text-text-muted py-6 text-center">
                正在检索知识库...
              </div>
            ) : results.length === 0 ? (
              <div className="text-sm text-text-muted py-6 text-center">
                未找到匹配的知识片段
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {results.map((r) => (
                  <SearchResultCard
                    key={r.chunk_id}
                    result={r}
                    query={activeQuery}
                  />
                ))}
              </div>
            )}
          </section>
        )}

        {/* 文档列表区 */}
        <section>
          <div className="flex items-center gap-2 mb-3 text-sm font-semibold text-text-primary">
            <svg
              className="w-4 h-4 opacity-70"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M3 1.5a1 1 0 0 1 1-1h5.5L13 4v9.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" />
              <path d="M9.5.5V4H13" />
            </svg>
            知识素材文档
            <span className="text-text-tertiary font-normal text-xs">
              · 共 {documents.length} 篇
            </span>
          </div>

          {loading ? (
            <div className="text-sm text-text-muted py-6 text-center">
              加载文档列表...
            </div>
          ) : error ? (
            <div className="text-sm text-error py-6 text-center">
              加载失败：{error}
            </div>
          ) : documents.length === 0 ? (
            <div className="text-sm text-text-muted py-6 text-center border border-dashed border-border-default rounded-md">
              暂无知识素材，拖入文件即可注入知识库
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {documents.map((doc) => {
                const meta = STATUS_META[doc.parse_status] ?? STATUS_META.pending;
                return (
                  <div
                    key={doc.id}
                    className="flex items-center gap-3 px-3 py-2.5 bg-bg-secondary border border-border-subtle rounded-md hover:border-border-default transition-colors"
                  >
                    {/* 类型 badge */}
                    <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-bg-tertiary text-text-secondary tracking-wider flex-shrink-0 min-w-[36px] text-center">
                      {typeBadge(doc.file_type)}
                    </span>

                    {/* 文件名 */}
                    <span
                      className="text-sm text-text-primary truncate flex-1 min-w-0"
                      title={doc.file_name}
                    >
                      {doc.file_name}
                    </span>

                    {/* 状态 badge */}
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-medium whitespace-nowrap flex-shrink-0 ${meta.cls}`}
                    >
                      {meta.label}
                    </span>

                    {/* 创建时间 */}
                    <span className="text-xs text-text-muted font-mono whitespace-nowrap flex-shrink-0 hidden sm:block">
                      {formatDate(doc.created_at)}
                    </span>

                    {/* 删除按钮 */}
                    <button
                      type="button"
                      onClick={() => void handleDelete(doc)}
                      disabled={deletingId === doc.id}
                      aria-label="删除文档"
                      className="text-text-muted hover:text-error transition-colors cursor-pointer border-none bg-transparent p-1 disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                    >
                      {deletingId === doc.id ? (
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 16 16"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          className="animate-spin"
                        >
                          <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
                        </svg>
                      ) : (
                        <svg
                          width="14"
                          height="14"
                          viewBox="0 0 16 16"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                        >
                          <path d="M3 4h10M6 4V2.5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1V4M5 4l.5 9a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1l.5-9" />
                        </svg>
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>

      {/* 应届生经历深度挖掘抽屉 (US-36) */}
      <MaterialMiningDrawer
        open={miningDrawerOpen}
        onClose={() => setMiningDrawerOpen(false)}
        onKnowledgeRefresh={() => {
          fetchDocuments();
          onKnowledgeRefresh?.();
        }}
      />
    </div>
  );
}

/** 单条检索结果卡片 */
function SearchResultCard({
  result,
  query,
}: {
  result: SearchResult;
  query: string;
}) {
  // score 通常为 0-1 的余弦相似度，转为百分比
  const pct = Math.max(0, Math.min(100, Math.round(result.score * 100)));

  return (
    <div className="bg-bg-secondary border border-border-subtle rounded-md p-3 hover:border-border-default transition-colors">
      {/* 顶部：来源 + 分数 */}
      <div className="flex items-center gap-2 mb-2">
        <svg
          className="w-3.5 h-3.5 text-text-muted flex-shrink-0"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M3 1.5a1 1 0 0 1 1-1h5.5L13 4v9.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" />
          <path d="M9.5.5V4H13" />
        </svg>
        <span
          className="text-xs text-text-secondary truncate flex-1 min-w-0"
          title={result.source_file}
        >
          {result.source_file}
        </span>
        {/* 相似度分数 */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <div className="w-12 h-1 bg-bg-tertiary rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${pct}%`,
                background:
                  'linear-gradient(90deg, var(--color-brand-primary), var(--color-brand-secondary))',
              }}
            />
          </div>
          <span className="text-xs font-mono text-text-tertiary min-w-[36px] text-right">
            {pct}%
          </span>
        </div>
      </div>

      {/* 匹配文本片段 */}
      <p className="text-sm text-text-secondary leading-relaxed break-words m-0">
        {highlightMatch(result.chunk_text, query)}
      </p>
    </div>
  );
}
