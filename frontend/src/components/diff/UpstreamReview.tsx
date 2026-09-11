import type { UpstreamChanges } from '@/lib/api';
import { upstreamValue } from '@/lib/upstreamDisplay';

export default function UpstreamReview({snapshot, source, busy, stale, onRefresh, onAction}: {
 snapshot: UpstreamChanges; source: string; busy: boolean; stale: boolean;
 onRefresh: () => void; onAction: (action: 'accept' | 'retain' | 'all', field?: string) => void;
}) {
 const conflicts = Object.values(snapshot.changes).some(change => change.conflict);
 return <section aria-label="上游变更审阅" className="px-4 pb-3 space-y-3 max-h-[50vh] overflow-y-auto">
  <p className="text-sm text-text-secondary">来自 {source} · 逐项选择采用上游内容或保留当前内容。</p>
  {stale && <div role="alert" className="text-sm text-error">内容已变化，请刷新后重新审阅。<button disabled={busy} onClick={onRefresh} className="ml-2 underline min-h-11">刷新变更</button></div>}
  {Object.entries(snapshot.changes).map(([field, change]) => <article key={field} className="bg-bg-primary border border-border-default rounded-md p-3 space-y-2">
   <h3 className="text-sm font-medium text-text-primary">{change.label || change.section || field}{change.conflict && <span className="ml-2 text-error">双方均已修改 · 冲突</span>}</h3>
   {change.conflict && <div className="text-xs text-text-secondary whitespace-pre-wrap break-words"><strong>共同基准</strong><p>{upstreamValue(change.base)}</p></div>}
   <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-sm">
    <div className="bg-bg-secondary rounded p-2 whitespace-pre-wrap break-words"><strong>当前内容</strong><p>{upstreamValue(change.old)}</p></div>
    <div className="bg-bg-secondary rounded p-2 whitespace-pre-wrap break-words"><strong>上游内容</strong><p>{upstreamValue(change.new)}</p></div>
   </div>
   <div className="flex flex-wrap gap-2"><button disabled={busy || stale} onClick={()=>onAction('accept',field)} className="min-h-11 px-3 rounded bg-brand-primary text-white text-sm disabled:opacity-40">采用上游</button><button disabled={busy || stale} onClick={()=>onAction('retain',field)} className="min-h-11 px-3 rounded border border-border-default text-sm disabled:opacity-40">保留当前</button></div>
  </article>)}
  {conflicts && <p className="text-sm text-error">存在冲突，请逐项处理后再全部接受。</p>}
  <button disabled={busy || stale || conflicts || !snapshot.count} onClick={()=>onAction('all')} className="min-h-11 w-full rounded bg-brand-primary text-white text-sm disabled:opacity-40">{busy ? '处理中…' : '全部接受合并'}</button>
 </section>;
}
