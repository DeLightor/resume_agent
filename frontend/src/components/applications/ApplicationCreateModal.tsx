import { useEffect, useRef, useState } from 'react';
import { createApplication } from '@/lib/api';
import { applicationPayload, localDateTimeToUtc } from '@/lib/applicationTracker';
import type { ApplicationRecord } from '@/types/application';
import type { ResumeNode } from '@/types/tree';

interface Props {
  node: ResumeNode;
  structuredJD: Record<string, unknown> | null;
  onClose: () => void;
  onCreated: (record: ApplicationRecord) => void;
}

export default function ApplicationCreateModal({ node, structuredJD, onClose, onCreated }: Props) {
  const initialCompany = typeof structuredJD?.company === 'string' ? structuredJD.company : node.company ?? '';
  const initialRole = typeof structuredJD?.job_title === 'string' ? structuredJD.job_title : '';
  const [company, setCompany] = useState(initialCompany);
  const [role, setRole] = useState(initialRole);
  const [jobUrl, setJobUrl] = useState('');
  const [nextAction, setNextAction] = useState('');
  const [followUpAt, setFollowUpAt] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => { firstField.current?.focus(); }, []);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape' && !saving) onClose(); };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose, saving]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const date = localDateTimeToUtc(followUpAt);
    if (followUpAt && !date) { setError('跟进时间格式无效，请重新选择。'); return; }
    setSaving(true); setError('');
    try {
      const record = await createApplication(applicationPayload({
        resume_node_id: node.node_id, company, role,
        job_url: jobUrl || null, jd_snapshot: structuredJD,
        next_action: nextAction || null, follow_up_at: date, notes: notes || null,
      }));
      onCreated(record);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '创建投递记录失败，请重试。');
    } finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4" role="presentation">
      <section role="dialog" aria-modal="true" aria-labelledby="application-create-title" className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-xl border border-border-default bg-bg-primary shadow-xl">
        <div className="flex items-start justify-between px-6 py-5 border-b border-border-subtle">
          <div><h2 id="application-create-title" className="text-lg font-semibold text-text-primary">记录投递</h2><p className="mt-1 text-sm text-text-secondary">将冻结「{node.title || node.node_id}」当前版本，之后编辑不会影响这次投递。</p></div>
          <button type="button" aria-label="关闭记录投递表单" disabled={saving} onClick={onClose} className="min-w-11 min-h-11 rounded-md text-text-secondary hover:bg-bg-hover focus-visible:ring-2 focus-visible:ring-brand-primary cursor-pointer disabled:cursor-not-allowed">×</button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          {error && <p role="alert" className="rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">{error}</p>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block text-sm text-text-primary">公司 <span aria-hidden="true">*</span><input ref={firstField} required value={company} onChange={(e) => setCompany(e.target.value)} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-brand-primary" /></label>
            <label className="block text-sm text-text-primary">岗位 <span aria-hidden="true">*</span><input required value={role} onChange={(e) => setRole(e.target.value)} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-brand-primary" /></label>
          </div>
          <label className="block text-sm text-text-primary">职位链接<input type="url" value={jobUrl} onChange={(e) => setJobUrl(e.target.value)} placeholder="https://…" className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-brand-primary" /></label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="block text-sm text-text-primary">下一步<input value={nextAction} onChange={(e) => setNextAction(e.target.value)} placeholder="例如：准备一面" className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-brand-primary" /></label>
            <label className="block text-sm text-text-primary">跟进时间<input type="datetime-local" value={followUpAt} onChange={(e) => setFollowUpAt(e.target.value)} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-brand-primary" /></label>
          </div>
          <label className="block text-sm text-text-primary">备注<textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="mt-1 w-full rounded-md border border-border-default bg-bg-secondary px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-brand-primary" /></label>
          <div className="flex justify-end gap-3 pt-2"><button type="button" disabled={saving} onClick={onClose} className="min-h-11 rounded-md border border-border-default px-4 text-sm text-text-secondary hover:bg-bg-hover focus-visible:ring-2 focus-visible:ring-brand-primary cursor-pointer disabled:cursor-not-allowed">取消</button><button type="submit" disabled={saving} className="min-h-11 rounded-md bg-brand-primary px-4 text-sm font-medium text-white hover:opacity-90 focus-visible:ring-2 focus-visible:ring-brand-primary cursor-pointer disabled:cursor-not-allowed">{saving ? '保存中…' : '创建投递记录'}</button></div>
        </form>
      </section>
    </div>
  );
}
