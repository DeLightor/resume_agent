import { useEffect, useMemo, useRef, useState } from 'react';
import { contentDiff, applyChoices } from '@/lib/contentDiff';
import { updateNode } from '@/lib/api';
import type { ResumeNode } from '@/types/tree';
const labels: Record<string, string> = { personal_info: '个人信息', contact: '联系方式', name: '名称', summary: '自我评价', experience: '工作经历', projects: '项目经历', skills: '技能', education: '教育背景', awards: '获奖经历', publications: '论文与专利', certificates: '证书', company: '公司', role: '岗位', period: '时间', highlights: '经历要点', description: '描述', tech_stack: '技术栈', hard_skills: '专业技能', soft_skills: '通用技能', context: '说明', school: '学校', degree: '学历', major: '专业' };
export interface DraftReview { node: ResumeNode; content: Record<string, unknown>; baseVersion: number }
export default function ContentDraftReview({ draft, onClose, onApplied }: { draft: DraftReview; onClose: () => void; onApplied: (node: ResumeNode) => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const changes = useMemo(() => contentDiff(draft.node.content_json ?? {}, draft.content), [draft]);
  const [choices, setChoices] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => { setChoices({}); setError(''); }, [draft]);
  const remaining = changes.filter(c => choices[c.id] === undefined).length;
  async function apply() {
    setBusy(true); setError('');
    try {
      const content = applyChoices(draft.node.content_json ?? {}, changes, new Set(Object.keys(choices).filter(k => choices[k])));
      const saved = await updateNode(draft.node.node_id, { content_json: content, expected_version: draft.baseVersion });
      onApplied(saved);
    } catch (e) { setError(e instanceof Error ? e.message : '保存失败，请重试'); }
    finally { setBusy(false); }
  }
  function show(value: unknown): string {
    if (value === undefined || value === null) return '（无）';
    if (Array.isArray(value)) return value.map((item, index) => `${index + 1}. ${show(item)}`).join('\n');
    if (typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${labels[key] ?? key}：${show(item)}`).join('\n');
    return String(value);
  }
  return <dialog ref={dialog} onCancel={e => { e.preventDefault(); if (!busy) onClose(); }} aria-labelledby="draft-title" className="m-auto w-[min(760px,95vw)] max-h-[85vh] rounded-xl border border-border-default bg-bg-primary text-text-primary p-5 backdrop:bg-black/40">
    <h2 id="draft-title" className="text-lg font-semibold">审阅 AI 草稿 · {draft.node.title}</h2>
    <p className="text-sm text-text-secondary my-2">逐项接受或拒绝后确认。确认之前，节点内容保持原样。</p>
    <div className="flex gap-3 my-3"><button disabled={busy} onClick={() => setChoices(Object.fromEntries(changes.map(c => [c.id, true])))}>全部接受</button><button disabled={busy} onClick={() => setChoices(Object.fromEntries(changes.map(c => [c.id, false])))}>全部拒绝</button></div>
    <div className="space-y-3">{changes.map(c => <section key={c.id} className="border border-border-default rounded-md p-3">
      <h3 className="font-medium text-sm break-all">{c.path.map(key => typeof key === 'number' ? `第 ${key + 1} 项` : labels[key] ?? key).join(' › ')}</h3>
      <div className="grid grid-cols-2 gap-3 my-2 text-sm"><div><span className="text-text-tertiary">原内容</span><pre className="whitespace-pre-wrap break-words font-body">{show(c.before)}</pre></div><div><span className="text-text-tertiary">AI 建议</span><pre className="whitespace-pre-wrap break-words font-body">{show(c.after)}</pre></div></div>
      <div className="flex gap-3">{[true, false].map(accept => <button key={String(accept)} disabled={busy} aria-pressed={choices[c.id] === accept} onClick={() => setChoices(prev => ({...prev, [c.id]: accept}))} className={`px-3 py-2 rounded border ${choices[c.id] === accept ? 'bg-brand-primary text-white' : 'border-border-default'}`}>{accept ? '接受' : '拒绝'}</button>)}</div>
    </section>)}</div>
    {!changes.length && <p className="py-4">AI 草稿与当前内容相同，无需修改。</p>}
    {error && <p role="alert" className="text-error my-3">{error}。草稿已保留，可取消后刷新节点再生成。</p>}
    <footer className="flex items-center gap-3 mt-4"><span className="text-sm flex-1">{remaining ? `还有 ${remaining} 项待选择` : '已完成审阅'}</span><button disabled={busy} onClick={onClose} className="px-3 py-2">取消草稿</button><button disabled={busy || remaining > 0 || !changes.length} onClick={apply} className="px-4 py-2 rounded bg-brand-primary text-white disabled:opacity-40">{busy ? '保存中…' : '确认应用'}</button></footer>
  </dialog>;
}
