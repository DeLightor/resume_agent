// frontend/src/components/template/ResumePreview.tsx
// 简历预览组件（US-8）
// 根据 templateId 选择 CSS 样式，渲染 name → contact → experience → projects → skills
// 三种模板视觉差异：
// - modern：简洁分隔线（border-bottom），灰色标题
// - classic：色块标题条（背景色 + 白字），主题色 #1C487C
// - tech：紧凑布局，技能以 inline 标签形式，主题色 #0F766E

interface ResumePreviewProps {
  /** AI 生成的简历数据，null 时显示空状态 */
  resumeData: Record<string, unknown> | null;
  /** 当前模板 id，决定视觉风格 */
  templateId: string;
}

/** 各模板主题色（与后端 templates.py 对齐） */
const THEME_COLORS: Record<string, string> = {
  modern: '#2563eb',
  classic: '#1C487C',
  tech: '#0F766E',
};

function getThemeColor(templateId: string): string {
  return THEME_COLORS[templateId] ?? THEME_COLORS.modern;
}

/** 安全读取字符串字段 */
function asString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

/** 安全读取字符串数组 */
function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === 'string');
}

/** 安全读取对象数组 */
function asObjectArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (v): v is Record<string, unknown> =>
      typeof v === 'object' && v !== null && !Array.isArray(v),
  );
}

/** 段落标题：根据模板渲染不同风格 */
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
    // classic: 色块标题条（背景色 + 白字）
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
    // tech: 紧凑，主题色标题 + 分隔线
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
  // modern: 灰色标题 + 浅灰分隔线
  return (
    <div className="text-sm font-semibold text-text-secondary mt-4 mb-2 pb-1 border-b border-border-subtle">
      {title}
    </div>
  );
}

/** 工作经历条目 */
function ExperienceItem({
  exp,
  compact,
}: {
  exp: Record<string, unknown>;
  compact: boolean;
}) {
  const role = asString(exp.role);
  const company = asString(exp.company);
  const period = asString(exp.period);
  const highlights = asStringArray(exp.highlights);

  return (
    <div className={compact ? 'mb-2' : 'mb-3'}>
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-text-primary">
          {role}
          {company && (
            <span className="text-text-tertiary font-normal ml-1">
              | {company}
            </span>
          )}
        </span>
        {period && (
          <span className="text-[11px] text-text-muted">{period}</span>
        )}
      </div>
      {highlights.length > 0 && (
        <ul className={compact ? 'mt-0.5 space-y-0.5' : 'mt-1 space-y-1'}>
          {highlights.map((h, i) => (
            <li
              key={i}
              className="text-xs text-text-secondary flex gap-1.5 leading-snug"
            >
              <span className="text-text-muted flex-shrink-0">·</span>
              <span>{h}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 项目经历条目 */
function ProjectItem({
  proj,
  compact,
}: {
  proj: Record<string, unknown>;
  compact: boolean;
}) {
  const name = asString(proj.name);
  const role = asString(proj.role);
  const period = asString(proj.period);
  const description = asString(proj.description);
  const techStack = asStringArray(proj.tech_stack);

  return (
    <div className={compact ? 'mb-2' : 'mb-3'}>
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-text-primary">
          {name}
          {role && (
            <span className="text-text-tertiary font-normal ml-1">
              | {role}
            </span>
          )}
        </span>
        {period && (
          <span className="text-[11px] text-text-muted">{period}</span>
        )}
      </div>
      {description && (
        <p className="text-xs text-text-secondary mt-0.5 leading-snug">
          {description}
        </p>
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

/** 技能段落：tech 模板以 inline 标签形式展示，其余逐行展示 */
function SkillsSection({
  skills,
  templateId,
  themeColor,
}: {
  skills: Record<string, unknown>;
  templateId: string;
  themeColor: string;
}) {
  const categories = [
    { key: 'tech_stack', label: '技术栈' },
    { key: 'hard_skills', label: '硬技能' },
    { key: 'soft_skills', label: '软技能' },
  ];

  const isEmpty = categories.every((cat) => {
    const items = asObjectArray(skills[cat.key]);
    return items.length === 0;
  });
  if (isEmpty) return null;

  if (templateId === 'tech') {
    // tech: inline 标签横排（背景色块）
    return (
      <div className="space-y-1.5">
        {categories.map((cat) => {
          const items = asObjectArray(skills[cat.key]);
          if (items.length === 0) return null;
          return (
            <div key={cat.key}>
              <span className="text-xs font-medium mr-1.5" style={{ color: themeColor }}>
                {cat.label}:
              </span>
              {items.map((item, i) => {
                const name = asString(item.name);
                const context = asString(item.context);
                const label = context ? `${name}（${context}）` : name;
                return (
                  <span
                    key={i}
                    className="inline-block text-[11px] px-1.5 py-0.5 rounded mr-1 mb-1 text-text-primary"
                    style={{
                      backgroundColor: `${themeColor}18`,
                      color: themeColor,
                    }}
                  >
                    {label}
                  </span>
                );
              })}
            </div>
          );
        })}
      </div>
    );
  }

  // modern / classic: 逐行展示
  return (
    <div className="space-y-1.5">
      {categories.map((cat) => {
        const items = asObjectArray(skills[cat.key]);
        if (items.length === 0) return null;
        return (
          <div key={cat.key}>
            <div className="text-xs font-medium text-text-secondary mb-0.5">
              {cat.label}
            </div>
            {items.map((item, i) => {
              const name = asString(item.name);
              const context = asString(item.context);
              return (
                <div key={i} className="text-xs text-text-secondary flex gap-1.5 leading-snug">
                  <span className="text-text-muted flex-shrink-0">·</span>
                  {context ? (
                    <span>
                      <span className="text-text-primary font-medium">{name}</span>
                      <span className="text-text-tertiary">：{context}</span>
                    </span>
                  ) : (
                    <span className="text-text-primary">{name}</span>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

export default function ResumePreview({
  resumeData,
  templateId,
}: ResumePreviewProps) {
  // 空状态
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

  const name = asString(resumeData.name) || '简历';
  const email = asString(resumeData.email);
  const phone = asString(resumeData.phone);
  const experiences = asObjectArray(resumeData.experience);
  const projects = asObjectArray(resumeData.projects);
  const skillsRaw = resumeData.skills;
  const skills =
    skillsRaw && typeof skillsRaw === 'object' && !Array.isArray(skillsRaw)
      ? (skillsRaw as Record<string, unknown>)
      : {};

  const contactParts: string[] = [];
  if (email) contactParts.push(email);
  if (phone) contactParts.push(phone);

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

      {/* 工作经历 */}
      {experiences.length > 0 && (
        <section>
          <SectionHeader
            title="工作经历"
            templateId={templateId}
            themeColor={themeColor}
          />
          {experiences.map((exp, i) => (
            <ExperienceItem key={i} exp={exp} compact={compact} />
          ))}
        </section>
      )}

      {/* 项目经历 */}
      {projects.length > 0 && (
        <section>
          <SectionHeader
            title="项目经历"
            templateId={templateId}
            themeColor={themeColor}
          />
          {projects.map((proj, i) => (
            <ProjectItem key={i} proj={proj} compact={compact} />
          ))}
        </section>
      )}

      {/* 技能 */}
      {Object.keys(skills).length > 0 && (
        <section>
          <SectionHeader
            title="技能"
            templateId={templateId}
            themeColor={themeColor}
          />
          <SkillsSection
            skills={skills}
            templateId={templateId}
            themeColor={themeColor}
          />
        </section>
      )}

      {/* 全部段落为空时的提示 */}
      {experiences.length === 0 &&
        projects.length === 0 &&
        Object.keys(skills).length === 0 && (
          <div className="text-center text-sm text-text-muted py-8">
            简历内容为空，请先生成各段落
          </div>
        )}
    </div>
  );
}
