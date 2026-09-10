// frontend/src/components/personal/PersonalInfoForm.tsx
// US-12: 个人信息管理表单
// - 4 个折叠区域：联系方式 / 求职意向 / 教育背景 / 自我评价
// - 共享节点草稿队列（800ms），版本校验后保存
// - 节点切换时重新加载
// - 支持从知识库提取

import { useState } from 'react';
import { extractPersonalInfo } from '@/lib/api';
import { useNodeDraftById } from '@/hooks/useNodeDraft';
import { emptyPersonalInfo, type PersonalInfo, type EducationItem } from '@/types/personal';

interface PersonalInfoFormProps {
  /** 当前选中的节点 ID */
  nodeId: string | null;
}


const FIELD_LABELS = {
  // contact
  name: '姓名',
  gender: '性别',
  birth_date: '出生年月',
  phone: '电话',
  email: '邮箱',
  location: '所在城市',
  website: '个人网站',
  github: 'GitHub',
  linkedin: 'LinkedIn',
  // job_intention
  target_role: '目标岗位',
  expected_salary: '期望薪资',
  availability: '到岗时间',
  // education
  school: '学校',
  degree: '学历',
  major: '专业',
  period: '时间段',
  // summary
  summary: '自我评价',
};

function Field({
  label,
  value,
  onChange,
  type = 'text',
  placeholder = '',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] text-text-tertiary">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="text-xs px-2 py-1 rounded border border-border-subtle bg-bg-elevated text-text-primary focus:outline-none focus:border-brand-primary transition-colors"
      />
    </label>
  );
}

function Section({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-border-subtle">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-text-primary hover:bg-bg-tertiary transition-colors"
      >
        <span>{title}</span>
        <svg
          width="10"
          height="10"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`transition-transform ${open ? 'rotate-90' : ''}`}
        >
          <path d="M6 4l4 4-4 4" />
        </svg>
      </button>
      {open && <div className="px-3 pb-3 space-y-2">{children}</div>}
    </div>
  );
}

/** Fill missing legacy fields without dropping extra imported values. */
function personalInfo(value: unknown): PersonalInfo {
  const empty = emptyPersonalInfo();
  if (!value || typeof value !== 'object' || Array.isArray(value)) return empty;
  const raw = value as Partial<PersonalInfo>;
  return {
    ...empty, ...raw,
    contact: { ...empty.contact, ...raw.contact },
    job_intention: { ...empty.job_intention, ...raw.job_intention },
    education: Array.isArray(raw.education) ? raw.education.map(item => ({ ...item })) : [],
    summary: typeof raw.summary === 'string' ? raw.summary : '',
    avatar: typeof raw.avatar === 'string' ? raw.avatar : '',
  };
}

export default function PersonalInfoForm({ nodeId }: PersonalInfoFormProps) {
  const draft = useNodeDraftById(nodeId);
  const { status: saveStatus, loading } = draft;
  const [extracting, setExtracting] = useState(false);
  const [extractMsg, setExtractMsg] = useState<string | null>(null);
  const info = personalInfo(draft.content?.personal_info);

  function updateInfo(change: (current: PersonalInfo) => void) {
    draft.edit(content => {
      const current = personalInfo(content.personal_info);
      change(current);
      content.personal_info = current;
    });
  }
  function updateContact(field: keyof PersonalInfo['contact'], value: string) {
    updateInfo(current => { current.contact[field] = value; });
  }

  // US-24: 头像上传 — 读取文件、裁剪为方形、转 base64
  function handleAvatarUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = ''; // 允许重复选同一文件

    if (!file.type.match(/^image\/(jpeg|jpg|png)$/)) {
      setExtractMsg('仅支持 JPG/PNG 格式');
      setTimeout(() => setExtractMsg(null), 3000);
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setExtractMsg('图片大小不能超过 10MB');
      setTimeout(() => setExtractMsg(null), 3000);
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        // 裁剪为正方形（取中心区域）
        const size = Math.min(img.width, img.height);
        const offsetX = (img.width - size) / 2;
        const offsetY = (img.height - size) / 2;
        const canvas = document.createElement('canvas');
        const targetSize = 200; // 输出 200x200
        canvas.width = targetSize;
        canvas.height = targetSize;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.drawImage(img, offsetX, offsetY, size, size, 0, 0, targetSize, targetSize);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        updateInfo(current => { current.avatar = dataUrl; });
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  }

  function handleRemoveAvatar() {
    updateInfo(current => { current.avatar = ''; });
  }
  function updateSummary(value: string) {
    updateInfo(current => { current.summary = value; });
  }
  function addEducation() {
    updateInfo(current => { current.education.push({ school: '', degree: '', major: '', period: '' }); });
  }
  function updateEducation(idx: number, field: keyof EducationItem, value: string) {
    updateInfo(current => { if (current.education[idx]) current.education[idx][field] = value; });
  }
  function removeEducation(idx: number) {
    updateInfo(current => { current.education.splice(idx, 1); });
  }

  // 从知识库提取
  async function handleExtract() {
    setExtracting(true);
    setExtractMsg(null);
    try {
      const extracted = await extractPersonalInfo();
      draft.edit(content => { content.personal_info = extracted; });
      if (!await draft.flush()) {
        setExtractMsg('提取结果已保留在草稿中，请处理保存提示。');
        return;
      }
      const name = extracted.contact.name || '';
      setExtractMsg(name ? `已提取：${name}` : '已提取个人信息');
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : '提取失败';
      setExtractMsg(msg);
    } finally {
      setExtracting(false);
      setTimeout(() => setExtractMsg(null), 3000);
    }
  }

  if (!nodeId) {
    return (
      <div className="px-3 py-3 border-b border-border-subtle">
        <div className="flex items-center gap-1.5 mb-1">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-brand-primary"
          >
            <circle cx="8" cy="5" r="3" />
            <path d="M2 14c0-3.3 2.7-6 6-6s6 2.7 6 6" />
          </svg>
          <span className="text-xs font-semibold text-text-primary">个人信息</span>
        </div>
        <div className="text-[10px] text-text-muted">
          请在中栏版本树中选中一个节点后填写
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <svg
          className="animate-spin w-4 h-4 text-text-tertiary"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M8 1.5a6.5 6.5 0 1 0 6.5 6.5" />
        </svg>
      </div>
    );
  }

  const statusText = {
    idle: '',
    pending: '待保存…',
    conflict: '版本冲突',
    saving: '保存中...',
    saved: '已保存',
    error: '保存失败',
  }[saveStatus];

  return (
    <div className="flex flex-col" onCompositionStart={() => draft.setComposing(true)} onCompositionEnd={() => draft.setComposing(false)}>
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <div className="flex items-center gap-1.5">
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="text-brand-primary"
          >
            <circle cx="8" cy="5" r="3" />
            <path d="M2 14c0-3.3 2.7-6 6-6s6 2.7 6 6" />
          </svg>
          <span className="text-xs font-semibold text-text-primary">个人信息</span>
          {statusText && (
            <span
              className={`text-[10px] ${saveStatus === 'error' ? 'text-error' : 'text-text-muted'}`}
            >
              {statusText}
            </span>
          )}
        </div>
        <button
          onClick={handleExtract}
          disabled={extracting || !draft.content}
          className="text-[10px] px-2 py-0.5 rounded border border-border-subtle text-text-secondary hover:border-brand-primary hover:text-brand-primary transition-colors disabled:opacity-50"
          title="从知识库上传的简历中提取个人信息"
        >
          {extracting ? '提取中...' : '从知识库提取'}
        </button>
      </div>
      {extractMsg && (
        <div className="px-3 pb-1 text-[10px] text-text-muted">
          {extractMsg}
        </div>
      )}

      {(draft.error || draft.loadError) && (
        <div role="alert" className="px-3 py-2 text-xs text-error">
          {draft.error || draft.loadError}
          {draft.loadError ? <button onClick={() => void draft.retryLoad()} className="ml-2 underline">重试加载</button>
            : saveStatus === 'conflict' ? <button onClick={() => { if (window.confirm('重新加载将丢弃本地未保存草稿，是否继续？')) void draft.reload(); }} className="ml-2 underline">重新加载服务端版本</button>
            : <button onClick={() => void draft.flush()} className="ml-2 underline">重试保存</button>}
        </div>
      )}
      <fieldset disabled={!draft.content}>
      {/* US-24: 头像上传 */}
      <div className="flex items-center gap-3 px-3 py-3 border-b border-border-subtle">
        {/* 头像预览 */}
        <div className="relative flex-shrink-0">
          {info.avatar ? (
            <img
              src={info.avatar}
              alt="头像"
              className="w-14 h-14 rounded-md object-cover border border-border-default"
            />
          ) : (
            <div className="w-14 h-14 rounded-md bg-gradient-to-br from-brand-primary to-brand-secondary flex items-center justify-center text-white text-lg font-bold">
              {info.contact.name?.charAt(0) || '?'}
            </div>
          )}
        </div>
        {/* 上传/移除按钮 */}
        <div className="flex flex-col gap-1">
          <label className="cursor-pointer text-[10px] px-2 py-1 rounded border border-border-subtle text-text-secondary hover:border-brand-primary hover:text-brand-primary transition-colors text-center">
            {info.avatar ? '更换头像' : '上传头像'}
            <input
              type="file"
              accept="image/jpeg,image/png,image/jpg"
              onChange={handleAvatarUpload}
              className="hidden"
            />
          </label>
          {info.avatar && (
            <button
              onClick={handleRemoveAvatar}
              className="text-[10px] text-error hover:underline"
            >
              移除
            </button>
          )}
          <span className="text-[9px] text-text-muted">JPG/PNG, ≤10MB</span>
        </div>
      </div>

      {/* 联系方式 */}
      <Section title="联系方式" defaultOpen={true}>
        <div className="grid grid-cols-2 gap-2">
          <Field
            label={FIELD_LABELS.name}
            value={info.contact.name}
            onChange={(v) => updateContact('name', v)}
            placeholder="张三"
          />
          <Field
            label={FIELD_LABELS.gender}
            value={info.contact.gender}
            onChange={(v) => updateContact('gender', v)}
            placeholder="男/女"
          />
          <Field
            label={FIELD_LABELS.birth_date}
            value={info.contact.birth_date}
            onChange={(v) => updateContact('birth_date', v)}
            placeholder="1995-01"
          />
          <Field
            label={FIELD_LABELS.phone}
            value={info.contact.phone}
            onChange={(v) => updateContact('phone', v)}
            placeholder="13800138000"
          />
          <Field
            label={FIELD_LABELS.email}
            value={info.contact.email}
            onChange={(v) => updateContact('email', v)}
            placeholder="email@example.com"
          />
          <Field
            label={FIELD_LABELS.location}
            value={info.contact.location}
            onChange={(v) => updateContact('location', v)}
            placeholder="北京"
          />
          <Field
            label={FIELD_LABELS.website}
            value={info.contact.website}
            onChange={(v) => updateContact('website', v)}
            placeholder="https://"
          />
          <Field
            label={FIELD_LABELS.github}
            value={info.contact.github}
            onChange={(v) => updateContact('github', v)}
            placeholder="https://github.com/"
          />
          <Field
            label={FIELD_LABELS.linkedin}
            value={info.contact.linkedin}
            onChange={(v) => updateContact('linkedin', v)}
            placeholder="https://linkedin.com/"
          />
        </div>
      </Section>

      {/* 教育背景 */}
      <Section title="教育背景">
        {info.education.length === 0 && (
          <div className="text-[10px] text-text-muted text-center py-2">
            暂无教育背景记录
          </div>
        )}
        {info.education.map((edu, idx) => (
          <div
            key={idx}
            className="space-y-1.5 p-2 rounded border border-border-subtle bg-bg-elevated"
          >
            <div className="grid grid-cols-2 gap-2">
              <Field
                label={FIELD_LABELS.school}
                value={edu.school}
                onChange={(v) => updateEducation(idx, 'school', v)}
                placeholder="清华大学"
              />
              <Field
                label={FIELD_LABELS.degree}
                value={edu.degree}
                onChange={(v) => updateEducation(idx, 'degree', v)}
                placeholder="本科"
              />
              <Field
                label={FIELD_LABELS.major}
                value={edu.major}
                onChange={(v) => updateEducation(idx, 'major', v)}
                placeholder="计算机科学"
              />
              <Field
                label={FIELD_LABELS.period}
                value={edu.period}
                onChange={(v) => updateEducation(idx, 'period', v)}
                placeholder="2018-2022"
              />
            </div>
            <button
              onClick={() => removeEducation(idx)}
              className="text-[10px] text-error hover:underline"
            >
              删除
            </button>
          </div>
        ))}
        <button
          onClick={addEducation}
          className="w-full text-xs px-2 py-1 rounded border border-dashed border-border-default text-text-secondary hover:border-brand-primary hover:text-brand-primary transition-colors"
        >
          + 添加教育背景
        </button>
      </Section>

      {/* 自我评价 */}
      <Section title="自我评价">
        <label className="flex flex-col gap-0.5">
          <textarea
            value={info.summary}
            onChange={(e) => updateSummary(e.target.value)}
            placeholder="3 年后端开发经验，熟悉..."
            rows={4}
            className="text-xs px-2 py-1.5 rounded border border-border-subtle bg-bg-elevated text-text-primary focus:outline-none focus:border-brand-primary transition-colors resize-none"
          />
        </label>
      </Section>
      </fieldset>
    </div>
  );
}
