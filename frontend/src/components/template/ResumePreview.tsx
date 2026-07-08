// frontend/src/components/template/ResumePreview.tsx
// 简历预览组件（US-8 + US-12 + US-15 增强）
// 渲染完整简历：个人信息 → 自我评价 → 工作经历 → 项目经历 → 技能 → 教育背景
// US-15: 支持内联编辑（summary/experience/projects highlights 可直接修改）
// 兼容两种数据源：
// 1. AI 生成数据（扁平结构：name/email/phone 在顶层，skills 是对象）
// 2. 上传解析数据（嵌套结构：basic.name/basic.phone，skills 是字符串数组，含 personal_info）

import { useState, useEffect } from 'react';

interface ResumePreviewProps {
  /** 简历数据（AI 生成或节点 content_json），null 时显示空状态 */
  resumeData: Record<string, unknown> | null;
  /** 当前模板 id，决定视觉风格 */
  templateId: string;
  /** US-14: 单段重新生成回调 */
  onRegenerateSection?: (section: string) => void;
  /** US-14: 正在重新生成的段落 key */
  generatingSection?: string | null;
  /** US-15: 段落编辑回调（section + data） */
  onEditSection?: (section: string, data: unknown) => void;
  /** US-15: 高亮字段（缺失字段标注） */
  highlightFields?: Set<string>;
}

const THEME_COLORS: Record<string, string> = {
  modern: '#2563eb',
  classic: '#1C487C',
  tech: '#0F766E',
};

function getThemeColor(templateId: string): string {
  return THEME_COLORS[templateId] ?? '#2563eb';
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === 'string');
}

function asObjectArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (v): v is Record<string, unknown> =>
      typeof v === 'object' && v !== null && !Array.isArray(v),
  );
}

/** 从 resumeData 中提取姓名（兼容 basic.name / personal_info.contact.name / 顶层 name） */
function extractName(data: Record<string, unknown>): string {
  const basic = data.basic;
  if (basic && typeof basic === 'object' && !Array.isArray(basic)) {
    const name = asString((basic as Record<string, unknown>).name);
    if (name) return name;
  }
  const pi = data.personal_info;
  if (pi && typeof pi === 'object' && !Array.isArray(pi)) {
    const contact = (pi as Record<string, unknown>).contact;
    if (contact && typeof contact === 'object') {
      const name = asString((contact as Record<string, unknown>).name);
      if (name) return name;
    }
  }
  return asString(data.name) || '简历';
}

/** 提取联系方式字符串列表 */
function extractContactParts(data: Record<string, unknown>): string[] {
  const parts: string[] = [];
  const basic = data.basic;
  const pi = data.personal_info;

  // 优先从 personal_info.contact 读取
  if (pi && typeof pi === 'object' && !Array.isArray(pi)) {
    const contact = (pi as Record<string, unknown>).contact;
    if (contact && typeof contact === 'object') {
      const c = contact as Record<string, unknown>;
      const phone = asString(c.phone);
      const email = asString(c.email);
      const location = asString(c.location);
      if (phone) parts.push(phone);
      if (email) parts.push(email);
      if (location) parts.push(location);
      const github = asString(c.github);
      if (github) parts.push(github);
    }
  }

  // fallback: basic
  if (parts.length === 0 && basic && typeof basic === 'object') {
    const b = basic as Record<string, unknown>;
    const phone = asString(b.phone);
    const email = asString(b.email);
    if (phone) parts.push(phone);
    if (email) parts.push(email);
  }

  // fallback: 顶层
  if (parts.length === 0) {
    const phone = asString(data.phone);
    const email = asString(data.email);
    if (phone) parts.push(phone);
    if (email) parts.push(email);
  }

  return parts;
}

/** 提取自我评价 */
function extractSummary(data: Record<string, unknown>): string {
  const pi = data.personal_info;
  if (pi && typeof pi === 'object' && !Array.isArray(pi)) {
    const summary = asString((pi as Record<string, unknown>).summary);
    if (summary) return summary;
  }
  return asString(data.summary);
}

/** 提取教育背景 */
function extractEducation(data: Record<string, unknown>): Array<Record<string, unknown>> {
  const pi = data.personal_info;
  if (pi && typeof pi === 'object' && !Array.isArray(pi)) {
    const edu = (pi as Record<string, unknown>).education;
    const items = asObjectArray(edu);
    if (items.length > 0) return items;
  }
  return asObjectArray(data.education);
}

/** 提取技能（兼容对象格式和字符串数组格式） */
function extractSkills(data: Record<string, unknown>): {
  isObject: boolean;
  obj: Record<string, unknown>;
  strArray: string[];
} {
  const skillsRaw = data.skills;
  if (skillsRaw && typeof skillsRaw === 'object' && !Array.isArray(skillsRaw)) {
    return { isObject: true, obj: skillsRaw as Record<string, unknown>, strArray: [] };
  }
  if (Array.isArray(skillsRaw)) {
    return { isObject: false, obj: {}, strArray: asStringArray(skillsRaw) };
  }
  return { isObject: false, obj: {}, strArray: [] };
}

// === US-15: 可编辑组件 ===

function EditableSummary({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);

  // 节点切换时同步
  useEffect(() => {
    setText(value);
  }, [value]);

  function handleBlur() {
    setEditing(false);
    if (text !== value) {
      onChange(text);
    }
  }

  if (editing) {
    return (
      <textarea
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={handleBlur}
        className="w-full text-sm text-text-secondary leading-relaxed p-2 border border-brand-primary rounded bg-white resize-none focus:outline-none focus:ring-1 focus:ring-brand-primary"
        rows={4}
      />
    );
  }

  return (
    <p
      onClick={() => setEditing(true)}
      className="text-xs text-text-secondary leading-relaxed cursor-text hover:bg-blue-50 rounded p-1 -m-1 transition-colors"
      title="点击编辑"
    >
      {value || placeholder || '点击编辑'}
    </p>
  );
}

function EditableText({
  value,
  onChange,
  placeholder,
  className,
}: {
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);

  useEffect(() => {
    setText(value);
  }, [value]);

  function handleBlur() {
    setEditing(false);
    if (text !== value) {
      onChange(text);
    }
  }

  if (editing) {
    return (
      <input
        autoFocus
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={handleBlur}
        style={{ display: 'inline-block', width: '500px' }}
        className={`border border-brand-primary rounded px-2 py-1 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-brand-primary ${className ?? ''}`}
      />
    );
  }

  return (
    <span
      onClick={(e) => {
        e.stopPropagation();
        setEditing(true);
      }}
      className={`cursor-text hover:bg-blue-50 rounded px-0.5 ${className ?? ''}`}
      title="点击编辑"
    >
      {value || placeholder || '—'}
    </span>
  );
}

function EditableHighlights({
  highlights,
  onChange,
}: {
  highlights: string[];
  onChange: (val: string[]) => void;
}) {
  const [items, setItems] = useState(highlights);

  useEffect(() => {
    setItems(highlights);
  }, [highlights]);

  function updateItem(idx: number, val: string) {
    const newItems = [...items];
    newItems[idx] = val;
    setItems(newItems);
    onChange(newItems);
  }

  function addItem() {
    const newItems = [...items, ''];
    setItems(newItems);
  }

  function removeItem(idx: number) {
    const newItems = items.filter((_, i) => i !== idx);
    setItems(newItems);
    onChange(newItems);
  }

  return (
    <ul className="mt-1 space-y-1">
      {items.map((h, i) => (
        <li key={i} className="text-xs text-text-secondary flex gap-1.5 items-start leading-snug">
          <span className="text-text-muted flex-shrink-0 mt-0.5">·</span>
          <EditableText
            value={h}
            onChange={(val) => updateItem(i, val)}
            className="flex-1"
          />
          <button
            onClick={(e) => { e.stopPropagation(); removeItem(i); }}
            className="bg-error text-white rounded w-4 h-4 flex items-center justify-center text-[10px] flex-shrink-0 mt-0.5 hover:bg-red-600"
            title="删除此条"
          >
            ✕
          </button>
        </li>
      ))}
      <li>
        <button
          onClick={(e) => { e.stopPropagation(); addItem(); }}
          className="text-[11px] text-brand-primary hover:underline mt-1"
        >
          + 添加一条
        </button>
      </li>
    </ul>
  );
}

// === 主组件 ===

function SectionHeader({
  title,
  templateId,
  themeColor,
}: {
  title: string;
  templateId: string;
  themeColor: string;
}) {
  if (templateId === 'classic') {
    return (
      <div
        className="px-2 py-1.5 text-sm font-semibold text-white mt-4 mb-2 rounded-sm"
        style={{ backgroundColor: themeColor }}
      >
        {title}
      </div>
    );
  }
  if (templateId === 'tech') {
    return (
      <div
        className="text-sm font-semibold mt-3 mb-1.5 pb-1 border-b"
        style={{
          color: themeColor,
          borderBottomColor: `${themeColor}40`,
        }}
      >
        {title}
      </div>
    );
  }
  return (
    <div className="text-sm font-semibold text-text-secondary mt-4 mb-2 pb-1 border-b border-border-subtle">
      {title}
    </div>
  );
}

function ExperienceItem({
  exp,
  compact,
  onEdit,
  onDelete,
}: {
  exp: Record<string, unknown>;
  compact: boolean;
  onEdit?: (data: Record<string, unknown>) => void;
  onDelete?: () => void;
}) {
  const role = asString(exp.role);
  const company = asString(exp.company);
  const period = asString(exp.period);
  const highlights = asStringArray(exp.highlights);

  function handleFieldChange(field: string, val: string) {
    onEdit?.({ ...exp, [field]: val });
  }

  function handleHighlightsChange(newHighlights: string[]) {
    onEdit?.({ ...exp, highlights: newHighlights });
  }

  return (
    <div className={`${compact ? 'mb-2' : 'mb-3'} group relative`}>
      {onDelete && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="absolute top-0 right-0 bg-error text-white rounded w-5 h-5 flex items-center justify-center text-[10px] hover:bg-red-600 z-10 opacity-0 group-hover:opacity-100 transition-opacity"
          title="删除此条经历"
        >
          ✕
        </button>
      )}
      <div className="flex items-baseline justify-between pr-7">
        <span className="text-sm font-medium text-text-primary">
          <EditableText value={role} onChange={(v) => handleFieldChange('role', v)} placeholder="职位" />
          {company && (
            <span className="text-text-tertiary font-normal ml-1">
              | <EditableText value={company} onChange={(v) => handleFieldChange('company', v)} />
            </span>
          )}
        </span>
        {period && (
          <span className="text-[11px] text-text-muted">
            <EditableText value={period} onChange={(v) => handleFieldChange('period', v)} />
          </span>
        )}
      </div>
      {highlights.length > 0 && (
        <EditableHighlights highlights={highlights} onChange={handleHighlightsChange} />
      )}
    </div>
  );
}

function ProjectItemView({
  proj,
  compact,
  onEdit,
  onDelete,
}: {
  proj: Record<string, unknown>;
  compact: boolean;
  onEdit?: (data: Record<string, unknown>) => void;
  onDelete?: () => void;
}) {
  const name = asString(proj.name);
  const role = asString(proj.role);
  const period = asString(proj.period);
  const description = asString(proj.description);
  const techStack = asStringArray(proj.tech_stack);

  function handleFieldChange(field: string, val: string) {
    onEdit?.({ ...proj, [field]: val });
  }

  function handleHighlightsChange(newHighlights: string[]) {
    onEdit?.({ ...proj, highlights: newHighlights });
  }

  const highlights = asStringArray(proj.highlights);

  return (
    <div className={`${compact ? 'mb-2' : 'mb-3'} group relative`}>
      {onDelete && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="absolute top-0 right-0 bg-error text-white rounded w-5 h-5 flex items-center justify-center text-[10px] hover:bg-red-600 z-10 opacity-0 group-hover:opacity-100 transition-opacity"
          title="删除此项目"
        >
          ✕
        </button>
      )}
      <div className="flex items-baseline justify-between pr-7">
        <span className="text-sm font-medium text-text-primary">
          <EditableText value={name} onChange={(v) => handleFieldChange('name', v)} placeholder="项目名" />
          {role && (
            <span className="text-text-tertiary font-normal ml-1">
              | <EditableText value={role} onChange={(v) => handleFieldChange('role', v)} />
            </span>
          )}
        </span>
        {period && (
          <span className="text-[11px] text-text-muted">
            <EditableText value={period} onChange={(v) => handleFieldChange('period', v)} />
          </span>
        )}
      </div>
      {description !== null && (
        <div className="mt-0.5">
          <EditableSummary value={description} onChange={(v) => handleFieldChange('description', v)} placeholder="点击添加项目描述" />
        </div>
      )}
      {highlights.length > 0 && (
        <EditableHighlights highlights={highlights} onChange={handleHighlightsChange} />
      )}
      {techStack.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {techStack.map((tech, i) => (
            <span
              key={i}
              className="text-[10px] px-1.5 py-0.5 rounded bg-bg-tertiary text-text-secondary"
            >
              {tech}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function EducationItemView({
  edu,
  compact,
}: {
  edu: Record<string, unknown>;
  compact: boolean;
}) {
  const school = asString(edu.school);
  const degree = asString(edu.degree);
  const major = asString(edu.major);
  const period = asString(edu.period);

  return (
    <div className={compact ? 'mb-1.5' : 'mb-2'}>
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-text-primary">
          {school}
          {degree && (
            <span className="text-text-tertiary font-normal ml-1">
              | {degree}
            </span>
          )}
        </span>
        {period && (
          <span className="text-[11px] text-text-muted">{period}</span>
        )}
      </div>
      {major && (
        <p className="text-xs text-text-secondary mt-0.5">{major}</p>
      )}
    </div>
  );
}

export default function ResumePreview({
  resumeData,
  templateId,
  onRegenerateSection,
  generatingSection,
  onEditSection,
  // highlightFields 暂未使用，预留给后续高亮标注
}: ResumePreviewProps) {
  if (!resumeData) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-text-muted py-12">
        <svg
          className="w-10 h-10 mb-3 opacity-40"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        >
          <rect x="2" y="2" width="12" height="12" rx="1" />
          <path d="M5 6h6M5 9h6M5 12h4" />
        </svg>
        <span className="text-sm">请先生成简历内容</span>
      </div>
    );
  }

  const themeColor = getThemeColor(templateId);
  const compact = templateId === 'tech';

  const name = extractName(resumeData);
  const contactParts = extractContactParts(resumeData);
  const summary = extractSummary(resumeData);
  const experiences = asObjectArray(resumeData.experience);
  const projects = asObjectArray(resumeData.projects);
  const education = extractEducation(resumeData);
  const { isObject: skillsIsObject, obj: skillsObj, strArray: skillsStrArray } =
    extractSkills(resumeData);

  // 获取 section_order（US-13）
  const sectionOrderRaw = resumeData.section_order;
  const sectionOrder: Array<{ key: string; title: string; visible: boolean }> =
    Array.isArray(sectionOrderRaw)
      ? sectionOrderRaw
          .filter(
            (s): s is Record<string, unknown> =>
              typeof s === 'object' && s !== null,
          )
          .map((s) => ({
            key: asString(s.key),
            title: asString(s.title),
            visible: s.visible !== false,
          }))
      : [];

  // 段落内容映射
  const sectionRenderers: Record<
    string,
    { title: string; render: () => React.ReactNode }
  > = {
    summary: {
      title: '自我评价',
      render: () =>
        summary !== null ? (
          <EditableSummary
            value={summary}
            onChange={(val) => onEditSection?.('summary', val)}
          />
        ) : null,
    },
    experience: {
      title: '工作经历',
      render: () => (
        <>
          {experiences.map((exp, i) => (
            <ExperienceItem
              key={i}
              exp={exp}
              compact={compact}
              onEdit={(data) => {
                const newExp = [...experiences];
                newExp[i] = data;
                onEditSection?.('experience', newExp);
              }}
              onDelete={() => {
                const newExp = experiences.filter((_, idx) => idx !== i);
                onEditSection?.('experience', newExp);
              }}
            />
          ))}
          <button
            onClick={(e) => {
              e.stopPropagation();
              const newItem = { role: '新职位', company: '', period: '', highlights: [] };
              onEditSection?.('experience', [...experiences, newItem]);
            }}
            className="text-[11px] text-brand-primary hover:underline mt-1"
          >
            + 添加工作经历
          </button>
        </>
      ),
    },
    projects: {
      title: '项目经历',
      render: () => (
        <>
          {projects.map((proj, i) => (
            <ProjectItemView
              key={i}
              proj={proj}
              compact={compact}
              onEdit={(data) => {
                const newProjects = [...projects];
                newProjects[i] = data;
                onEditSection?.('projects', newProjects);
              }}
              onDelete={() => {
                const newProjects = projects.filter((_, idx) => idx !== i);
                onEditSection?.('projects', newProjects);
              }}
            />
          ))}
          <button
            onClick={(e) => {
              e.stopPropagation();
              const newItem = { name: '新项目', role: '', period: '', description: '', highlights: [], tech_stack: [] };
              onEditSection?.('projects', [...projects, newItem]);
            }}
            className="text-[11px] text-brand-primary hover:underline mt-1"
          >
            + 添加项目经历
          </button>
        </>
      ),
    },
    skills: {
      title: '技能',
      render: () => {
        if (skillsIsObject && Object.keys(skillsObj).length > 0) {
          return (
            <div className="space-y-1.5">
              {[
                { key: 'tech_stack', label: '技术栈' },
                { key: 'hard_skills', label: '硬技能' },
                { key: 'soft_skills', label: '软技能' },
              ].map((cat) => {
                const items = asObjectArray(skillsObj[cat.key]);
                if (items.length === 0) return null;
                return (
                  <div key={cat.key}>
                    <div className="text-xs font-medium text-text-secondary mb-0.5">
                      {cat.label}
                    </div>
                    {items.map((item, i) => {
                      const sName = asString(item.name);
                      const context = asString(item.context);
                      return (
                        <div
                          key={i}
                          className="text-xs text-text-secondary flex gap-1.5 items-start leading-snug"
                        >
                          <span className="text-text-muted flex-shrink-0 mt-0.5">·</span>
                          <EditableText
                            value={sName}
                            onChange={(val) => {
                              const newSkills = JSON.parse(JSON.stringify(skillsObj));
                              if (!newSkills[cat.key]) newSkills[cat.key] = [];
                              if (!newSkills[cat.key][i]) newSkills[cat.key][i] = {};
                              newSkills[cat.key][i].name = val;
                              onEditSection?.('skills', newSkills);
                            }}
                            className="font-medium text-text-primary"
                          />
                          <span className="text-text-tertiary">：</span>
                          <EditableText
                            value={context}
                            onChange={(val) => {
                              const newSkills = JSON.parse(JSON.stringify(skillsObj));
                              if (!newSkills[cat.key]) newSkills[cat.key] = [];
                              if (!newSkills[cat.key][i]) newSkills[cat.key][i] = {};
                              newSkills[cat.key][i].context = val;
                              onEditSection?.('skills', newSkills);
                            }}
                            className="flex-1"
                          />
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          );
        }
        if (skillsStrArray.length > 0) {
          return (
            <div className="flex flex-wrap gap-1">
              {skillsStrArray.map((skill, i) => (
                <EditableText
                  key={i}
                  value={skill}
                  onChange={(val) => {
                    const newArr = [...skillsStrArray];
                    newArr[i] = val;
                    onEditSection?.('skills', newArr);
                  }}
                  className="text-[11px] px-1.5 py-0.5 rounded bg-bg-tertiary text-text-secondary"
                />
              ))}
            </div>
          );
        }
        return null;
      },
    },
    education: {
      title: '教育背景',
      render: () =>
        education.length > 0 ? (
          <>
            {education.map((edu, i) => (
              <EducationItemView key={i} edu={edu} compact={compact} />
            ))}
          </>
        ) : null,
    },
    awards: {
      title: '获奖经历',
      render: () => null,
    },
    publications: {
      title: '论文/专利',
      render: () => null,
    },
    certificates: {
      title: '证书',
      render: () => null,
    },
  };

  // 默认段落顺序（无 section_order 时）
  const defaultOrder = [
    'summary',
    'experience',
    'projects',
    'skills',
    'education',
    'awards',
    'publications',
    'certificates',
  ];

  const orderedSections =
    sectionOrder.length > 0
      ? sectionOrder.filter((s) => s.visible && sectionRenderers[s.key])
      : defaultOrder.map((key) => ({
          key,
          title: sectionRenderers[key]?.title ?? key,
          visible: true,
        }));

  const hasContent = orderedSections.some((s) => {
    const renderer = sectionRenderers[s.key];
    return renderer && renderer.render() !== null;
  });

  return (
    <div
      className={`mx-auto bg-white ${compact ? 'max-w-3xl p-4' : 'max-w-2xl p-6'} shadow-sm`}
      style={{ minHeight: '100%' }}
    >
      {/* 姓名 */}
      <h1
        className={`text-center font-bold text-text-primary ${compact ? 'text-xl mb-1' : 'text-2xl mb-2'}`}
        style={templateId === 'classic' ? { color: themeColor } : undefined}
      >
        {name}
      </h1>

      {/* 联系信息 */}
      {contactParts.length > 0 && (
        <div className="text-center text-xs text-text-tertiary mb-3">
          {contactParts.join(' | ')}
        </div>
      )}

      {/* 按排序渲染各段落 */}
      {orderedSections.map((section) => {
        const renderer = sectionRenderers[section.key];
        if (!renderer) return null;
        const content = renderer.render();
        if (content === null) return null;
        const isGenerating = generatingSection === section.key;
        return (
          <section key={section.key}>
            <div className="flex items-center justify-between">
              <SectionHeader
                title={section.title || renderer.title}
                templateId={templateId}
                themeColor={themeColor}
              />
              {onRegenerateSection && (
                <button
                  onClick={() => onRegenerateSection(section.key)}
                  disabled={isGenerating}
                  className="text-[10px] px-1.5 py-0.5 rounded text-text-muted hover:text-brand-primary hover:border-brand-primary border border-transparent transition-colors disabled:opacity-50"
                  title={`重新生成${section.title || renderer.title}`}
                >
                  {isGenerating ? '生成中...' : '↻'}
                </button>
              )}
            </div>
            {content}
          </section>
        );
      })}

      {/* 全部段落为空时的提示 */}
      {!hasContent && (
        <div className="text-center text-sm text-text-muted py-8">
          简历内容为空，请先生成各段落
        </div>
      )}
    </div>
  );
}
