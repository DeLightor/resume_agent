import { useCallback, useEffect, useState } from 'react';
import { ApiError, deleteApplication, getApplication, listApplications, restoreApplication, updateApplication } from '@/lib/api';
import { APPLICATION_STATUSES, localDateTimeToUtc, statusMeta, utcToLocalDateTime } from '@/lib/applicationTracker';
import type { ApplicationDetail, ApplicationRecord, ApplicationStatus } from '@/types/application';

const TONE_CLASS = { muted: 'bg-bg-tertiary text-text-secondary', brand: 'bg-brand-primary-muted text-brand-primary', warning: 'bg-warning/15 text-warning', success: 'bg-success/15 text-success', danger: 'bg-error/15 text-error' } as const;
const EVENT_LABEL: Record<string, string> = { created: '创建记录', status_changed: '变更状态', updated: '更新字段', deleted: '移入回收站', restored: '从回收站恢复' };

function dateText(value: string | null) { return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '未设置'; }

function jdSummary(value: Record<string, unknown> | null) {
  if (!value) return '未冻结职位描述';
  const company = typeof value.company === 'string' ? value.company : '';
  const title = typeof value.job_title === 'string' ? value.job_title : '';
  const skills = Array.isArray(value.hard_skills)
    ? value.hard_skills.filter((item): item is string => typeof item === 'string').slice(0, 4)
    : [];
  return [company, title, skills.length ? `技能：${skills.join('、')}` : ''].filter(Boolean).join(' · ') || '已冻结结构化 JD';
}

export default function ApplicationTrackerView() {
  const [items, setItems] = useState<ApplicationRecord[]>([]);
  const [status, setStatus] = useState<'all' | ApplicationStatus>('all');
  const [deleted, setDeleted] = useState<'exclude' | 'only'>('exclude');
  const [selected, setSelected] = useState<ApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try { setItems(await listApplications(status === 'all' ? undefined : status, deleted)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '加载投递记录失败。'); }
    finally { setLoading(false); }
  }, [status, deleted]);
  useEffect(() => { void load(); }, [load]);

  async function open(record: ApplicationRecord) {
    try { setSelected(await getApplication(record.id)); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '加载投递详情失败。'); }
  }
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const follow = String(form.get('follow_up_at') ?? '');
    const followUpAt = localDateTimeToUtc(follow);
    if (follow && !followUpAt) { setError('跟进时间格式无效。'); return; }
    setSaving(true); setError('');
    try {
      const record = await updateApplication(selected.id, {
        expected_version: selected.version, company: String(form.get('company') ?? ''), role: String(form.get('role') ?? ''),
        status: String(form.get('status')) as ApplicationStatus, status_change_note: String(form.get('status_change_note') ?? '') || null,
        job_url: String(form.get('job_url') ?? '') || null, next_action: String(form.get('next_action') ?? '') || null,
        follow_up_at: followUpAt, notes: String(form.get('notes') ?? '') || null,
      });
      setSelected(await getApplication(record.id)); await load();
    } catch (caught) {
      setError(caught instanceof ApiError && caught.code === 'VERSION_CONFLICT' ? '记录已在其他页面更新，已保留当前输入；请关闭后重新打开。' : caught instanceof Error ? caught.message : '保存失败。');
    } finally { setSaving(false); }
  }
  async function removeOrRestore() {
    if (!selected) return;
    setSaving(true); setError('');
    try {
      const record = selected.deleted_at ? await restoreApplication(selected.id, selected.version) : await deleteApplication(selected.id, selected.version);
      setSelected(await getApplication(record.id)); await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : '操作失败。'); }
    finally { setSaving(false); }
  }

  return <main className="flex-1 min-w-0 overflow-hidden bg-bg-primary"><div className="h-full overflow-y-auto p-6"><div className="flex flex-wrap items-center gap-3 border-b border-border-subtle pb-4"><div><h1 className="text-xl font-semibold text-text-primary">投递追踪</h1><p className="mt-1 text-sm text-text-secondary">每条记录冻结投递时的简历版本与职位上下文。</p></div><span role="status" aria-atomic="true" className="ml-auto rounded-full bg-error/10 px-3 py-1 text-xs text-error">逾期跟进 {items.filter((item) => item.is_overdue).length} 条</span></div>
    <div className="mt-4 flex flex-wrap gap-2" aria-label="投递状态筛选"><button aria-pressed={status === 'all'} onClick={() => setStatus('all')} className={`rounded-full px-3 py-2 text-xs cursor-pointer focus-visible:ring-2 focus-visible:ring-brand-primary ${status === 'all' ? 'bg-brand-primary text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-hover'}`}>全部</button>{APPLICATION_STATUSES.map((value) => <button key={value} aria-pressed={status === value} onClick={() => setStatus(value)} className={`rounded-full px-3 py-2 text-xs cursor-pointer focus-visible:ring-2 focus-visible:ring-brand-primary ${status === value ? 'bg-brand-primary text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-hover'}`}>{statusMeta(value).label}</button>)}<button aria-pressed={deleted === 'only'} onClick={() => setDeleted((old) => old === 'only' ? 'exclude' : 'only')} className={`rounded-full px-3 py-2 text-xs cursor-pointer focus-visible:ring-2 focus-visible:ring-brand-primary ${deleted === 'only' ? 'bg-brand-primary text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-hover'}`}>已删除</button></div>
    {error && <p role="alert" className="mt-4 rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">{error}</p>}
    {loading ? <p className="mt-8 text-sm text-text-secondary">正在加载投递记录…</p> : items.length === 0 ? <p className="mt-8 rounded-lg border border-dashed border-border-default p-8 text-center text-sm text-text-secondary">暂无记录。先在简历版本树选择一个节点，再点击“记录投递”。</p> : <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map((record) => { const meta = statusMeta(record.status); return <button key={record.id} onClick={() => void open(record)} className="text-left rounded-lg border border-border-default bg-bg-secondary p-4 transition-colors hover:bg-bg-hover focus-visible:ring-2 focus-visible:ring-brand-primary cursor-pointer"><div className="flex items-start gap-2"><span className={`rounded-full px-2 py-1 text-xs ${TONE_CLASS[meta.tone]}`}>{meta.label}</span>{record.is_overdue && <span className="rounded-full border border-error/30 px-2 py-1 text-xs text-error">逾期</span>}</div><h2 className="mt-3 font-medium text-text-primary">{record.company} · {record.role}</h2><p className="mt-2 text-xs text-text-secondary">版本：{record.resume_node_title} · v{record.resume_version}</p><p className="mt-1 text-xs text-text-secondary">跟进：{dateText(record.follow_up_at)}</p></button>; })}</div>}
    {selected && <aside role="dialog" aria-modal="true" aria-label="投递详情" className="fixed inset-y-0 right-0 z-[60] w-full max-w-xl overflow-y-auto border-l border-border-default bg-bg-primary shadow-xl"><div className="sticky top-0 flex items-center justify-between border-b border-border-subtle bg-bg-primary px-6 py-4"><div><h2 className="font-semibold text-text-primary">投递详情</h2><p className="text-xs text-text-secondary">简历快照 v{selected.resume_version}{selected.source_node_deleted ? ' · 原版本已在回收站' : ''}</p><div className="mt-2 rounded-md bg-bg-secondary px-3 py-2"><p className="text-[11px] uppercase tracking-wide text-text-tertiary">冻结的 JD 摘要</p><p className="mt-1 text-xs text-text-secondary">{jdSummary(selected.jd_snapshot)}</p></div></div><button aria-label="关闭投递详情" onClick={() => setSelected(null)} className="min-w-11 min-h-11 rounded-md text-text-secondary hover:bg-bg-hover focus-visible:ring-2 focus-visible:ring-brand-primary cursor-pointer">×</button></div><form onSubmit={save} className="space-y-4 p-6"><div className="grid grid-cols-2 gap-3"><label className="text-sm">公司<input name="company" defaultValue={selected.company} required className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary" /></label><label className="text-sm">岗位<input name="role" defaultValue={selected.role} required className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary" /></label></div><label className="block text-sm">状态<select name="status" defaultValue={selected.status} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary">{APPLICATION_STATUSES.map((value) => <option key={value} value={value}>{statusMeta(value).label}</option>)}</select></label><label className="block text-sm">状态说明<input name="status_change_note" placeholder="状态改变时记录原因" className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary" /></label><label className="block text-sm">职位链接<input name="job_url" type="url" defaultValue={selected.job_url ?? ''} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary" /></label><div className="grid grid-cols-2 gap-3"><label className="text-sm">下一步<input name="next_action" defaultValue={selected.next_action ?? ''} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary" /></label><label className="text-sm">跟进时间<input name="follow_up_at" type="datetime-local" defaultValue={utcToLocalDateTime(selected.follow_up_at)} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary" /></label></div><label className="block text-sm">备注<textarea name="notes" defaultValue={selected.notes ?? ''} rows={3} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 focus-visible:ring-2 focus-visible:ring-brand-primary" /></label><div className="flex gap-3"><button disabled={saving || selected.deleted_at !== null} type="submit" className="min-h-11 rounded-md bg-brand-primary px-4 text-sm text-white disabled:cursor-not-allowed">{saving ? '保存中…' : '保存修改'}</button><button disabled={saving} type="button" onClick={() => void removeOrRestore()} className="min-h-11 rounded-md border border-border-default px-4 text-sm text-text-secondary cursor-pointer disabled:cursor-not-allowed">{selected.deleted_at ? '恢复记录' : '移入回收站'}</button></div></form><section className="border-t border-border-subtle p-6"><h3 className="font-medium text-text-primary">时间线</h3><ol className="mt-3 space-y-3">{selected.events.map((event) => <li key={event.id} className="border-l-2 border-border-default pl-3 text-sm"><p className="text-text-primary">{EVENT_LABEL[event.event_type]}{event.from_status && event.to_status ? `：${statusMeta(event.from_status).label} → ${statusMeta(event.to_status).label}` : ''}</p>{event.note && <p className="mt-1 text-text-secondary">{event.note}</p>}{event.changed_fields.length > 0 && <p className="mt-1 text-xs text-text-secondary">修改：{event.changed_fields.join('、')}</p>}<time className="mt-1 block text-xs text-text-tertiary">{dateText(event.created_at)}</time></li>)}</ol></section></aside>}
  </div></main>;
}
