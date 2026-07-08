// frontend/src/components/personal/PersonalInfoForm.tsx
// US-12: 个人信息管理表单
// - 4 个折叠区域：联系方式 / 求职意向 / 教育背景 / 自我评价
// - 防抖保存（500ms），写入当前选中节点
// - 节点切换时重新加载
// - 支持从知识库提取

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getPersonalInfo,
  updatePersonalInfo,
  extractPersonalInfo,
} from '@/lib/api';
import { emptyPersonalInfo, type PersonalInfo, type EducationItem } from '@/types/personal';

interface PersonalInfoFormProps {
  /** 当前选中的节点 ID */
  nodeId: string | null;
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

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

export default function PersonalInfoForm({ nodeId }: PersonalInfoFormProps) {
  const [info, setInfo] = useState<PersonalInfo>(emptyPersonalInfo());
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractMsg, setExtractMsg] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextSave = useRef(false);

  // 节点切换时加载
  useEffect(() => {
    if (!nodeId) {
      setInfo(emptyPersonalInfo());
      return;
    }

    setLoading(true);
    getPersonalInfo(nodeId)
      .then((data) => {
        setInfo(data);
        skipNextSave.current = true;
      })
      .catch(() => {
        setInfo(emptyPersonalInfo());
      })
      .finally(() => setLoading(false));

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [nodeId]);

  // 防抖保存
  const triggerSave = useCallback(
    (newInfo: PersonalInfo) => {
      if (!nodeId || skipNextSave.current) {
        skipNextSave.current = false;
        return;
      }

      setSaveStatus('saving');
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(async () => {
        try {
          await updatePersonalInfo(nodeId, newInfo);
          setSaveStatus('saved');
          setTimeout(() => setSaveStatus('idle'), 1500);
        } catch {
          setSaveStatus('error');
        }
      }, 500);
    },
    [nodeId],
  );

  // 更新 contact 字段
  function updateContact(field: keyof PersonalInfo['contact'], value: string) {
    const newInfo = { ...info, contact: { ...info.contact, [field]: value } };
    setInfo(newInfo);
    triggerSave(newInfo);
  }

  // 求职意向不需要用户填写，由 JD 分析自动填充
  // function updateIntention(...) 已移除

  // 更新 summary
  function updateSummary(value: string) {
    const newInfo = { ...info, summary: value };
    setInfo(newInfo);
    triggerSave(newInfo);
  }

  // 教育背景操作
  function addEducation() {
    const newItem: EducationItem = { school: '', degree: '', major: '', period: '' };
    const newInfo = { ...info, education: [...info.education, newItem] };
    setInfo(newInfo);
    triggerSave(newInfo);
  }

  function updateEducation(idx: number, field: keyof EducationItem, value: string) {
    const newEdu = [...info.education];
    newEdu[idx] = { ...newEdu[idx], [field]: value };
    const newInfo = { ...info, education: newEdu };
    setInfo(newInfo);
    triggerSave(newInfo);
  }

  function removeEducation(idx: number) {
    const newInfo = {
      ...info,
      education: info.education.filter((_, i) => i !== idx),
    };
    setInfo(newInfo);
    triggerSave(newInfo);
  }

  // 从知识库提取
  async function handleExtract() {
    setExtracting(true);
    setExtractMsg(null);
    try {
      const extracted = await extractPersonalInfo();
      setInfo(extracted);
      skipNextSave.current = true;
      // 立即保存
      if (nodeId) {
        await updatePersonalInfo(nodeId, extracted);
        setSaveStatus('saved');
        setTimeout(() => setSaveStatus('idle'), 1500);
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
    saving: '保存中...',
    saved: '已保存',
    error: '保存失败',
  }[saveStatus];

  return (
    <div className="flex flex-col">
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
          disabled={extracting}
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
    </div>
  );
}
