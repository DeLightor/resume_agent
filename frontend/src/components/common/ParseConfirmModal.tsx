import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cancelParse, confirmParse } from '@/lib/api';
import type { ConfidenceLevel, ParseResponse, ParseTaskDetail, StructuredResume } from '@/types/resume';

const BASIC_LABELS = {
  name: '姓名', gender: '性别', birth_date: '出生年月', phone: '电话', email: '邮箱',
  location: '所在城市', website: '个人网站', github: 'GitHub', linkedin: 'LinkedIn',
};
const ENTRY_LABELS: Record<string, string> = {
  school: '学校', degree: '学历', major: '专业', period: '起止时间',
  company: '公司', role: '角色 / 职位', name: '项目名称', description: '项目描述',
};
const SECTIONS = ['education', 'experience', 'projects'] as const;
const SECTION_LABELS = { education: '教育经历', experience: '工作经历', projects: '项目经历' };
const EMPTY_ENTRIES = {
  education: { school: '', degree: '', major: '', period: '' },
  experience: { company: '', role: '', period: '', highlights: [] as string[] },
  projects: { name: '', role: '', description: '' },
};
const control = 'w-full min-w-0 rounded-md border bg-bg-primary px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-primary';
const button = 'min-h-10 rounded-md border border-border-default px-3 py-2 text-sm hover:bg-bg-hover focus-visible:ring-2 focus-visible:ring-brand-primary disabled:opacity-50';

function Badge({ level, edited }: { level: ConfidenceLevel; edited: boolean }) {
  return <span className={`text-xs ${edited ? 'text-brand-primary' : level === 'low' ? 'text-error' : level === 'medium' ? 'text-warning' : 'text-text-secondary'}`}>
    {edited ? '已修改 · 待确认' : `${{ high: '高', medium: '中', low: '低' }[level]}置信度`}
  </span>;
}

export default function ParseConfirmModal({ task, open, onClose, onConfirmed }: {
  task: ParseTaskDetail; open: boolean; onClose: () => void; onConfirmed: (result: ParseResponse) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [draft, setDraft] = useState<StructuredResume>(() => structuredClone(task.structured_resume!));
  const [changed, setChanged] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [error, setError] = useState('');
  const [direction, setDirection] = useState(task.structured_resume?.primary_direction ?? '');
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  function update(section: string, key: string, apply: (next: StructuredResume) => void) {
    setDraft((prev) => { const next = structuredClone(prev); apply(next); return next; });
    setChanged((prev) => new Set(prev).add(`${section}.${key}`));
  }
  function field(section: string, key: string, label: string, value: string | null, onChange: (value: string) => void, multiline = false) {
    const edited = changed.has(`${section}.${key}`) || changed.has(`${section}.*`);
    const level = task.confidence?.[section]?.[key] ?? 'low';
    const cls = `${control} ${level === 'low' && !edited ? 'border-error' : 'border-border-default'}`;
    return <label key={key} className={`flex min-w-0 flex-col gap-1.5 ${multiline ? 'sm:col-span-2' : ''}`}>
      <span className="flex flex-wrap items-center justify-between gap-2 text-sm text-text-secondary">{label}<Badge level={level} edited={edited} /></span>
      {multiline ? <textarea rows={3} className={cls} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
        : <input className={cls} value={value ?? ''} onChange={(e) => onChange(e.target.value)} />}
    </label>;
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true); setError('');
    try {
      const result = await confirmParse(task.task_id, { structured_resume: { ...draft, primary_direction: direction.trim() || draft.primary_direction }, apply_knowledge_personal_info: false, custom_direction: direction.trim() || undefined });
      onConfirmed(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : '确认失败，请重试；你的修改仍保留');
    } finally { savingRef.current = false; setSaving(false); }
  }

  return createPortal(<dialog ref={dialogRef} aria-labelledby="parse-confirm-title"
    onClick={(e) => e.stopPropagation()}
    onCancel={(e) => { e.preventDefault(); if (!savingRef.current) onClose(); }}
    className="m-auto max-h-[92dvh] w-[min(880px,94vw)] overflow-y-auto rounded-xl border border-border-default bg-bg-secondary p-0 text-left text-text-primary shadow-xl backdrop:bg-black/50">
    <form onSubmit={submit}>
      <header className="border-b border-border-default p-5">
        <h2 id="parse-confirm-title" className="text-lg font-semibold">确认简历解析结果</h2>
        <p className="mt-2 text-sm text-text-secondary">核对并修正后再入库。确认前不会创建版本或写入知识库。</p>
        <p className="mt-1 text-xs text-text-secondary">置信度表示与原文的匹配程度，不代表事实核验；低置信度内容请重点检查。</p>
      </header>
      <fieldset disabled={saving} className="min-w-0 space-y-6 p-5">
        {task.degraded && <div role="status" className="rounded-md border border-warning bg-bg-tertiary p-3 text-sm text-text-primary">云端解析不可用，已使用本地解析器，复杂排版可能识别不全。</div>}
        <section aria-labelledby="parse-basic-title">
          <h3 id="parse-basic-title" className="mb-3 font-semibold">基本信息</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {(Object.entries(BASIC_LABELS) as [keyof typeof BASIC_LABELS, string][]).map(([key, label]) => <div key={key} className="min-w-0">
              {field('basic', key, label, draft.basic[key], (value) => update('basic', key, (next) => { next.basic[key] = value; }))}
              {task.knowledge_personal_info?.contact?.[key] && task.knowledge_personal_info.contact[key] !== draft.basic[key] &&
                <div className="mt-2 rounded-md bg-bg-tertiary p-2 text-xs text-text-secondary break-words">
                  <span>知识库已有{label}：{task.knowledge_personal_info.contact[key]}</span>
                  <button type="button" className="ml-2 min-h-8 text-brand-primary underline" onClick={() => update('basic', key, (next) => { next.basic[key] = task.knowledge_personal_info!.contact[key]!; })}>采用知识库{label}</button>
                </div>}
            </div>)}
          </div>
        </section>
        {SECTIONS.map((section) => <section key={section} aria-label={SECTION_LABELS[section]}>
          <h3 className="mb-3 font-semibold">{SECTION_LABELS[section]}</h3>
          {section === 'education' && !!task.knowledge_personal_info?.education?.length && <details className="mb-3 rounded-md bg-bg-tertiary p-3 text-sm">
            <summary className="cursor-pointer">查看知识库已有教育经历（采用会替换下方教育经历）</summary>
            {task.knowledge_personal_info.education.map((edu, index) => <p key={index} className="mt-2 break-words">{[edu.school, edu.degree, edu.major, edu.period].filter(Boolean).join(' · ')}</p>)}
            <button type="button" className={`${button} mt-2`} onClick={() => update('education', '*', (next) => {
              next.education = task.knowledge_personal_info!.education.map((edu) => ({ school: edu.school ?? '', degree: edu.degree ?? '', major: edu.major ?? '', period: edu.period ?? '' }));
            })}>采用知识库教育经历</button>
          </details>}
          <div className="space-y-3">
            {draft[section].map((entry, index) => <div key={index} className="rounded-lg border border-border-default p-4">
              <div className="mb-3 flex items-center justify-between gap-3"><span className="text-sm">{SECTION_LABELS[section]} {index + 1}</span>
                <button type="button" className={button} aria-label={`移除${SECTION_LABELS[section]} ${index + 1}`} onClick={() => update(section, '*', (next) => { next[section].splice(index, 1); })}>移除条目</button>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {Object.entries(entry).filter(([key]) => key !== 'highlights').map(([key, value]) => field(section, `${index}.${key}`, ENTRY_LABELS[key] ?? key, value as string | null, (value) => update(section, `${index}.${key}`, (next) => {
                  Object.assign(next[section][index], { [key]: value });
                }), key === 'description'))}
              </div>
              {'highlights' in entry && <div className="mt-4 space-y-3">
                {entry.highlights.map((highlight, h) => <div key={h} className="flex items-end gap-2">
                  <div className="min-w-0 flex-1">{field(section, `${index}.highlights.${h}`, `工作成果 ${h + 1}`, highlight, (value) => update(section, `${index}.highlights.${h}`, (next) => { next.experience[index].highlights[h] = value; }), true)}</div>
                  <button type="button" className={button} aria-label={`移除工作成果 ${h + 1}`} onClick={() => update(section, '*', (next) => { next.experience[index].highlights.splice(h, 1); })}>移除</button>
                </div>)}
                <button type="button" className={button} onClick={() => update(section, '*', (next) => { next.experience[index].highlights.push(''); })}>添加工作成果</button>
              </div>}
            </div>)}
            <button type="button" className={button} onClick={() => update(section, '*', (next) => {
              if (section === 'education') next.education.push({ ...EMPTY_ENTRIES.education });
              if (section === 'experience') next.experience.push({ ...EMPTY_ENTRIES.experience, highlights: [] });
              if (section === 'projects') next.projects.push({ ...EMPTY_ENTRIES.projects });
            })}>添加{SECTION_LABELS[section]}</button>
          </div>
        </section>)}
        <section aria-label="技能">
          <h3 className="mb-3 font-semibold">技能</h3>
          <div className="space-y-3">{draft.skills.map((skill, index) => <div key={index} className="flex items-end gap-2">
            <div className="min-w-0 flex-1">{field('skills', `${index}`, `技能 ${index + 1}`, skill, (value) => update('skills', `${index}`, (next) => { next.skills[index] = value; }))}</div>
            <button type="button" className={button} aria-label={`移除技能 ${index + 1}`} onClick={() => update('skills', '*', (next) => { next.skills.splice(index, 1); })}>移除</button>
          </div>)}</div>
          <button type="button" className={`${button} mt-3`} onClick={() => update('skills', '*', (next) => { next.skills.push(''); })}>添加技能</button>
        </section>
        <label className="flex flex-col gap-2 text-sm">简历方向（可自定义）
          <input className={`${control} border-border-default`} value={direction} onChange={(e) => setDirection(e.target.value)} placeholder="例如：云安全、Java 后端、数据产品" />
        </label>
      </fieldset>
      <footer className="border-t border-border-default bg-bg-secondary p-5">
        {error && <p role="alert" className="mb-3 text-sm text-error">{error}</p>}
        <p className="mb-3 text-xs text-text-secondary">稍后确认会保留本页修改；刷新页面后将恢复最初的提取结果。</p>
        <div className="flex flex-wrap justify-end gap-3">
          <button type="button" disabled={saving} className={`${button} text-error`} onClick={async () => {
            if (!window.confirm('取消后将删除本次上传和解析结果，确定取消吗？')) return;
            setSaving(true);
            try { await cancelParse(task.task_id); onClose(); window.location.reload(); }
            catch (err) { setError(err instanceof Error ? err.message : '取消失败，请重试'); }
            finally { setSaving(false); }
          }}>取消本次上传</button>
          <button type="button" disabled={saving} className={button} onClick={onClose}>稍后确认</button>
          <button type="button" disabled={saving} className={button} onClick={onClose}>重新选择文件</button>
          <button type="submit" disabled={saving} className="min-h-10 rounded-md bg-brand-primary px-5 py-2 text-sm text-white hover:bg-brand-primary-hover focus-visible:ring-2 focus-visible:ring-brand-primary disabled:opacity-50">{saving ? '正在入库…' : '确认并入库'}</button>
        </div>
      </footer>
    </form>
  </dialog>, document.body);
}
