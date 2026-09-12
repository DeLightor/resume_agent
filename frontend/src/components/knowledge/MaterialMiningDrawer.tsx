// frontend/src/components/knowledge/MaterialMiningDrawer.tsx
// 应届生追问式冷启动（素材挖掘）向导抽屉 (US-36)
// 包含：分类选择、S-T-A-R 4步状态机问答、师兄点评与灵感参考、自动草稿恢复、STAR结构化提炼与向量语义查重、一键入库闭环。

import { useCallback, useEffect, useState } from 'react';
import {
  commitMiningToKnowledge,
  createMiningSession,
  deleteMiningSession,
  getMiningSession,
  getMiningSessions,
  getMiningTemplates,
  submitMiningAnswer,
  synthesizeMiningResult,
} from '@/lib/api';
import type {
  DuplicateCheckResult,
  MaterialMiningSession,
  MiningCategory,
  MiningStepAnswer,
  MiningTemplate,
  StarResult,
} from '@/types/mining';

interface MaterialMiningDrawerProps {
  open: boolean;
  onClose: () => void;
  onKnowledgeRefresh?: () => void;
}

const STEP_NAMES = [
  { step: 1, label: 'S · 背景目标', short: 'S' },
  { step: 2, label: 'T · 核心难点', short: 'T' },
  { step: 3, label: 'A · 动作方案', short: 'A' },
  { step: 4, label: 'R · 产出指标', short: 'R' },
  { step: 5, label: '⭐ 提炼入库', short: '成果' },
];

export default function MaterialMiningDrawer({
  open,
  onClose,
  onKnowledgeRefresh,
}: MaterialMiningDrawerProps) {
  // 模板列表
  const [templates, setTemplates] = useState<MiningTemplate[]>([]);
  // 当前会话
  const [session, setSession] = useState<MaterialMiningSession | null>(null);
  // 未完成草稿列表
  const [drafts, setDrafts] = useState<MaterialMiningSession[]>([]);

  // 新建会话表单状态
  const [selectedCategory, setSelectedCategory] =
    useState<MiningCategory>('course_project');
  const [titleInput, setTitleInput] = useState('');

  // 问答阶段输入
  const [answerInput, setAnswerInput] = useState('');
  const [submittingStep, setSubmittingStep] = useState(false);
  const [stepError, setStepError] = useState<string | null>(null);
  const [latestFeedback, setLatestFeedback] = useState<string | null>(null);

  // 成果提炼阶段状态
  const [synthesizing, setSynthesizing] = useState(false);
  const [starResult, setStarResult] = useState<StarResult | null>(null);
  const [dupCheck, setDupCheck] = useState<DuplicateCheckResult | null>(null);
  const [committing, setCommitting] = useState(false);
  const [commitSuccessMsg, setCommitSuccessMsg] = useState<string | null>(null);
  const [editingBulletIndex, setEditingBulletIndex] = useState<number | null>(
    null,
  );

  // 加载模板与进行中草稿
  const loadInitialData = useCallback(async () => {
    try {
      const [tpls, activeSessions] = await Promise.all([
        getMiningTemplates(),
        getMiningSessions('in_progress'),
      ]);
      setTemplates(tpls);
      setDrafts(activeSessions);
      if (activeSessions.length > 0 && !session) {
        // 发现活跃草稿，暂存提示
      }
    } catch (err) {
      console.error('加载素材挖掘模板或草稿失败:', err);
    }
  }, [session]);

  useEffect(() => {
    if (open) {
      void loadInitialData();
    }
  }, [open, loadInitialData]);

  // 获取当前类别的模板
  const currentTemplate = templates.find(
    (t) => t.category === (session?.category || selectedCategory),
  );

  // 获取当前步骤的追问题目与参考
  const currentStepInfo = currentTemplate?.steps.find(
    (s) => s.step === (session ? session.current_step : 1),
  );
  const answeredSteps: MiningStepAnswer[] = session
    ? Object.entries(session.context)
        .map(([key, user_answer]) => {
          const step = Number(key.replace('step_', ''));
          return {
            step,
            step_title: currentTemplate?.steps.find((item) => item.step === step)?.title ?? `第 ${step} 步`,
            question: currentTemplate?.steps.find((item) => item.step === step)?.question ?? '',
            user_answer,
          };
        })
        .filter((answer) => Number.isInteger(answer.step) && answer.step >= 1 && answer.step <= 4)
        .sort((a, b) => a.step - b.step)
    : [];

  // 开始新会话
  const handleStartSession = async () => {
    const trimmedTitle = titleInput.trim();
    if (!trimmedTitle) {
      setStepError('请填写经历或项目名称');
      return;
    }
    setStepError(null);
    setSubmittingStep(true);
    try {
      const newSession = await createMiningSession({
        category: selectedCategory,
        title: trimmedTitle,
      });
      setSession(newSession);
      setAnswerInput('');
      setLatestFeedback(null);
      setStarResult(null);
      setDupCheck(null);
      setCommitSuccessMsg(null);
    } catch (err) {
      setStepError(err instanceof Error ? err.message : '创建挖掘会话失败');
    } finally {
      setSubmittingStep(false);
    }
  };

  // 恢复草稿
  const handleResumeDraft = async (draft: MaterialMiningSession) => {
    try {
      const full = await getMiningSession(draft.id);
      setSession(full);
      setAnswerInput('');
      setStepError(null);
      setCommitSuccessMsg(null);

      // 如果已有提炼结果直接呈现
      if (full.star_result) {
        setStarResult(full.star_result);
      } else if (full.current_step >= 5) {
        // 已完成步骤4，触发提炼
        void triggerSynthesize(full.id);
      }
    } catch (err) {
      setStepError(err instanceof Error ? err.message : '恢复草稿失败');
    }
  };

  // 提交当前步骤回答
  const handleSubmitAnswer = async () => {
    if (!session) return;
    const answer = answerInput.trim();
    if (!answer) {
      setStepError('请回答本步骤的追问内容');
      return;
    }

    setSubmittingStep(true);
    setStepError(null);
    try {
      const res = await submitMiningAnswer(session.id, {
        step: session.current_step,
        answer,
      });
      setLatestFeedback(res.feedback);
      setAnswerInput('');

      // 重新拉取最新会话
      const updated = await getMiningSession(session.id);
      setSession(updated);

      if (updated.current_step >= 5) {
        // 步骤完成，自动触发 STAR 提炼与查重
        await triggerSynthesize(session.id);
      }
    } catch (err) {
      setStepError(err instanceof Error ? err.message : '提交回答失败');
    } finally {
      setSubmittingStep(false);
    }
  };

  // 触发提炼 STAR 成果与查重
  const triggerSynthesize = async (sessionId: string) => {
    setSynthesizing(true);
    setStepError(null);
    try {
      const res = await synthesizeMiningResult(sessionId, true);
      setStarResult(res.star_result);
      setDupCheck(res.duplicate_check);
      // 更新 session 对象
      const updated = await getMiningSession(sessionId);
      setSession(updated);
    } catch (err) {
      setStepError(err instanceof Error ? err.message : '提炼 STAR 成果失败');
    } finally {
      setSynthesizing(false);
    }
  };

  // 确认沉淀入知识库
  const handleCommit = async () => {
    if (!session) return;
    setCommitting(true);
    setStepError(null);
    try {
      const res = await commitMiningToKnowledge(session.id, starResult ?? undefined);
      setCommitSuccessMsg(
        `🎉 沉淀成功！文档已写入知识库并完成向量切片索引（共 ${res.chunk_count} 个切片）。`,
      );
      // 通知外部刷新
      onKnowledgeRefresh?.();
      // 更新草稿列表
      void loadInitialData();
    } catch (err) {
      setStepError(err instanceof Error ? err.message : '提交入库失败');
    } finally {
      setCommitting(false);
    }
  };

  // 删除或放弃草稿
  const handleDeleteDraft = async (id: string) => {
    if (!window.confirm('确定放弃并删除本次挖掘记录吗？')) return;
    try {
      await deleteMiningSession(id);
      if (session?.id === id) {
        setSession(null);
        setStarResult(null);
        setDupCheck(null);
      }
      void loadInitialData();
    } catch (err) {
      setStepError(err instanceof Error ? err.message : '删除草稿失败');
    }
  };

  // 修改 bullet point 内容
  const handleUpdateBullet = (index: number, val: string) => {
    if (!starResult) return;
    const newBullets = [...starResult.bullet_points];
    newBullets[index] = val;
    setStarResult({ ...starResult, bullet_points: newBullets });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/45 backdrop-blur-[2px] transition-all">
      {/* 遮罩背景点击 */}
      <div
        className="flex-1 cursor-pointer"
        onClick={() => {
          if (submittingStep || synthesizing || committing) return;
          onClose();
        }}
      />

      {/* 抽屉主体 */}
      <div className="w-full max-w-2xl bg-bg-primary h-full shadow-2xl flex flex-col border-l border-border-subtle overflow-hidden font-body animate-in slide-in-from-right duration-200">
        {/* 抽屉顶部 Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle bg-bg-secondary flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-lg bg-brand-primary-muted text-brand-primary">
              💡
            </div>
            <div>
              <div className="text-base font-semibold text-text-primary flex items-center gap-2">
                应届生经历深度挖掘
                <span className="text-[11px] px-2 py-0.5 rounded-full font-medium bg-brand-primary-muted text-brand-primary">
                  师兄追问式冷启动
                </span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">
                大作业、学术竞赛、实验室科研、社团活动与早期实习的 STAR
                结构化提炼
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-text-muted hover:text-text-primary p-1.5 rounded-md hover:bg-bg-tertiary transition-colors cursor-pointer border-none bg-transparent"
            aria-label="关闭抽屉"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* 步骤状态机进度条 */}
        {session && (
          <div className="px-6 py-2.5 bg-bg-tertiary/50 border-b border-border-subtle flex-shrink-0">
            <div className="flex items-center justify-between text-xs">
              {STEP_NAMES.map((item) => {
                const isCurrent = session.current_step === item.step;
                const isPassed = session.current_step > item.step;
                return (
                  <div
                    key={item.step}
                    className={`flex items-center gap-1.5 font-medium transition-colors ${
                      isCurrent
                        ? 'text-brand-primary'
                        : isPassed
                          ? 'text-text-secondary'
                          : 'text-text-muted'
                    }`}
                  >
                    <span
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-mono ${
                        isCurrent
                          ? 'bg-brand-primary text-white font-bold ring-2 ring-brand-primary/20'
                          : isPassed
                            ? 'bg-success/20 text-success'
                            : 'bg-bg-tertiary text-text-muted border border-border-default'
                      }`}
                    >
                      {isPassed ? '✓' : item.short}
                    </span>
                    <span className="hidden sm:inline">{item.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 抽屉可滚动正文区 */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* 全局错误提示 */}
          {stepError && (
            <div className="p-3 text-xs text-error bg-[rgba(220,38,38,0.08)] border border-[rgba(220,38,38,0.2)] rounded-lg flex items-center justify-between">
              <span>{stepError}</span>
              <button
                type="button"
                onClick={() => setStepError(null)}
                className="text-error font-bold ml-2 cursor-pointer bg-transparent border-none"
              >
                ×
              </button>
            </div>
          )}

          {/* 状态 1: 未开启挖掘会话，展示草稿与新建表单 */}
          {!session ? (
            <div className="space-y-6">
              {/* 未完成草稿提示 */}
              {drafts.length > 0 && (
                <div className="p-4 rounded-xl border border-brand-primary/20 bg-brand-primary-muted/20 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-text-primary flex items-center gap-1.5">
                      <span>📌</span> 发现 {drafts.length} 个未完成的挖掘草稿
                    </span>
                    <span className="text-xs text-text-muted">断点已暂存</span>
                  </div>
                  <div className="space-y-2">
                    {drafts.map((d) => (
                      <div
                        key={d.id}
                        className="flex items-center justify-between p-2.5 rounded-lg bg-bg-secondary border border-border-subtle"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-text-primary truncate">
                            {d.title}
                          </div>
                          <div className="text-xs text-text-muted">
                            进度：步骤 {d.current_step} / 4 · 最近更新:{' '}
                            {d.updated_at.slice(0, 16)}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                          <button
                            type="button"
                            onClick={() => void handleResumeDraft(d)}
                            className="px-3 py-1 text-xs font-medium text-white rounded bg-brand-primary hover:brightness-110 cursor-pointer border-none"
                          >
                            继续挖掘
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDeleteDraft(d.id)}
                            className="p-1 text-xs text-error hover:bg-error/10 rounded cursor-pointer border-none bg-transparent"
                            title="删除草稿"
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 新建挖掘入口 */}
              <div className="space-y-4">
                <div className="space-y-1">
                  <label className="text-sm font-semibold text-text-primary">
                    1. 选择你想挖掘的经历分类
                  </label>
                  <p className="text-xs text-text-muted">
                    即使零商业实习经历，扎实的课设或比赛也能成为简历亮点
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {templates.map((tpl) => {
                    const isSelected = selectedCategory === tpl.category;
                    return (
                      <div
                        key={tpl.category}
                        onClick={() => setSelectedCategory(tpl.category)}
                        className={`p-3.5 rounded-xl border cursor-pointer transition-all flex flex-col justify-between ${
                          isSelected
                            ? 'border-brand-primary bg-brand-primary-muted/20 ring-1 ring-brand-primary shadow-sm'
                            : 'border-border-default bg-bg-secondary hover:border-border-hover'
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-xl">{tpl.icon}</span>
                          <span className="text-sm font-semibold text-text-primary">
                            {tpl.title}
                          </span>
                        </div>
                        <p className="text-xs text-text-secondary line-clamp-2 leading-relaxed">
                          {tpl.description}
                        </p>
                      </div>
                    );
                  })}
                </div>

                <div className="space-y-2 pt-2">
                  <label className="text-sm font-semibold text-text-primary block">
                    2. 经历 / 项目名称
                  </label>
                  <input
                    type="text"
                    value={titleInput}
                    onChange={(e) => setTitleInput(e.target.value)}
                    placeholder={
                      selectedCategory === 'course_project'
                        ? '例如：基于 Raft 的分布式 KV 存储引擎'
                        : selectedCategory === 'competition'
                          ? '例如：全国大学生数学建模国家一等奖项目'
                          : selectedCategory === 'research'
                            ? '例如：多模态大模型细粒度图文对齐研究'
                            : selectedCategory === 'club'
                              ? '例如：高校 48 小时创客马拉松 Hackathon 统筹'
                              : '例如：基础平台部音视频转码网关开发实习'
                    }
                    className="w-full bg-bg-tertiary border border-border-default rounded-lg px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand-primary transition-colors"
                  />
                </div>

                <button
                  type="button"
                  onClick={handleStartSession}
                  disabled={submittingStep || !titleInput.trim()}
                  className="w-full py-2.5 px-4 rounded-lg text-sm font-medium text-white shadow transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer border-none flex items-center justify-center gap-2"
                  style={{
                    background:
                      'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
                  }}
                >
                  {submittingStep ? '正在启动向导...' : '🚀 开始挖掘 (进入 S-T-A-R 向导)'}
                </button>
              </div>
            </div>
          ) : session.current_step <= 4 && !starResult ? (
            /* 状态 2: S-T-A-R 4 步交互问答阶段 */
            <div className="space-y-5">
              {/* 会话顶部信息卡 */}
              <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
                <div className="flex items-center gap-2">
                  <span className="text-base">{currentTemplate?.icon}</span>
                  <span className="text-sm font-semibold text-text-primary">
                    {session.title}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded bg-bg-tertiary text-text-secondary">
                    {currentTemplate?.title}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => void handleDeleteDraft(session.id)}
                  className="text-xs text-text-muted hover:text-error cursor-pointer border-none bg-transparent"
                >
                  放弃本次
                </button>
              </div>

              {/* 上一步师兄点评反馈 */}
              {latestFeedback && (
                <div className="p-3.5 rounded-xl border border-success/30 bg-success/5 space-y-1">
                  <div className="text-xs font-semibold text-success flex items-center gap-1.5">
                    <span>🧑‍💻</span> 师兄点评
                  </div>
                  <p className="text-xs text-text-secondary leading-relaxed">
                    {latestFeedback}
                  </p>
                </div>
              )}

              {/* 师兄追问卡片 */}
              {currentStepInfo && (
                <div className="p-4 rounded-xl bg-bg-secondary border-l-4 border-brand-primary border border-border-subtle shadow-sm space-y-3">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-brand-primary">
                      {currentStepInfo.title}
                    </span>
                    <span className="text-[11px] text-text-muted">
                      第 {currentStepInfo.step} 步 / 共 4 步
                    </span>
                  </div>

                  <p className="text-sm font-medium text-text-primary leading-relaxed">
                    {currentStepInfo.question}
                  </p>

                  {/* 灵感参考示例 */}
                  <div className="pt-2 border-t border-border-subtle space-y-2">
                    <div className="flex items-center justify-between text-xs text-text-muted">
                      <span className="flex items-center gap-1">
                        <span>💡</span> 灵感参考（不知道怎么说？看这里）：
                      </span>
                      <button
                        type="button"
                        onClick={() => setAnswerInput(currentStepInfo.example)}
                        className="text-xs text-brand-primary hover:underline cursor-pointer border-none bg-transparent"
                      >
                        一键填入参考
                      </button>
                    </div>
                    <div className="p-2.5 rounded-lg bg-bg-tertiary text-xs text-text-secondary leading-relaxed italic border border-border-subtle">
                      {currentStepInfo.example}
                    </div>
                  </div>
                </div>
              )}

              {/* 用户回答输入框 */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-text-secondary">
                    你的回答（想到什么写什么，师兄会帮你做专业润色）：
                  </label>
                  <span className="text-[11px] font-mono text-text-muted">
                    {answerInput.length} 字
                  </span>
                </div>

                <textarea
                  rows={5}
                  value={answerInput}
                  onChange={(e) => setAnswerInput(e.target.value)}
                  placeholder="不用拘泥格式，真实还原你的细节与过程..."
                  className="w-full bg-bg-tertiary border border-border-default rounded-xl p-3.5 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand-primary transition-colors resize-none leading-relaxed"
                />
              </div>

              {/* 提交按钮与自动保存提示 */}
              <div className="flex items-center justify-between pt-2">
                <span className="text-xs text-text-muted flex items-center gap-1">
                  <span>💾</span> 草稿自动保存，随时可关闭
                </span>
                <button
                  type="button"
                  onClick={handleSubmitAnswer}
                  disabled={submittingStep || !answerInput.trim()}
                  className="py-2 px-5 rounded-lg text-sm font-medium text-white shadow transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer border-none flex items-center gap-2"
                  style={{
                    background:
                      'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
                  }}
                >
                  {submittingStep ? (
                    <>
                      <span className="animate-spin inline-block">⏳</span>{' '}
                      师兄思考反馈中...
                    </>
                  ) : session.current_step === 4 ? (
                    '完成追问，一键提炼 STAR 成果 →'
                  ) : (
                    '提交给师兄，进入下一步 →'
                  )}
                </button>
              </div>

              {/* 已问答历史展开 */}
              {answeredSteps.length > 0 && (
                  <details className="mt-4 pt-3 border-t border-border-subtle group">
                    <summary className="text-xs text-text-muted cursor-pointer hover:text-text-primary list-none flex items-center gap-1 select-none">
                      <span className="transition-transform group-open:rotate-90">
                        ▶
                      </span>
                      查看已记录的 {answeredSteps.length} 轮问答
                    </summary>
                    <div className="mt-3 space-y-2.5">
                      {answeredSteps.map(
                        (ans: MiningStepAnswer) => (
                          <div
                            key={ans.step}
                            className="p-2.5 rounded-lg bg-bg-tertiary text-xs space-y-1 border border-border-subtle"
                          >
                            <div className="font-semibold text-text-primary">
                              {ans.step_title}
                            </div>
                            <p className="text-text-secondary">{ans.user_answer}</p>
                          </div>
                        ),
                      )}
                    </div>
                  </details>
                )}
            </div>
          ) : (
            /* 状态 3: STAR 结构化成果预览、向量语义查重与落库闭环 */
            <div className="space-y-6">
              {synthesizing ? (
                <div className="py-16 text-center space-y-3">
                  <div className="text-3xl animate-bounce">🤖</div>
                  <div className="text-sm font-semibold text-text-primary">
                    AI 师兄正在深度提炼 STAR 简历要点...
                  </div>
                  <p className="text-xs text-text-muted">
                    正在执行知识库向量相似度检索与防重分析
                  </p>
                </div>
              ) : starResult ? (
                <div className="space-y-5">
                  {/* 成功提交提示 */}
                  {commitSuccessMsg ? (
                    <div className="p-4 rounded-xl border border-success/30 bg-success/10 space-y-2 text-center">
                      <div className="text-sm font-semibold text-success">
                        {commitSuccessMsg}
                      </div>
                      <p className="text-xs text-text-secondary">
                        现在可以在知识库列表与语义检索中随时调用该经历，打造定制化高匹配简历！
                      </p>
                      <button
                        type="button"
                        onClick={onClose}
                        className="mt-2 px-4 py-1.5 text-xs font-medium text-white rounded-lg bg-success hover:brightness-110 cursor-pointer border-none"
                      >
                        完成并关闭抽屉
                      </button>
                    </div>
                  ) : null}

                  {/* 向量语义查重状态栏 */}
                  {dupCheck && (
                    <div
                      className={`p-3.5 rounded-xl border flex items-start gap-3 ${
                        dupCheck.is_duplicate
                          ? 'border-warning/40 bg-warning/10 text-warning'
                          : 'border-success/30 bg-success/5 text-success'
                      }`}
                    >
                      <span className="text-lg flex-shrink-0">
                        {dupCheck.is_duplicate ? '⚠️' : '✅'}
                      </span>
                      <div className="text-xs space-y-1">
                        <div className="font-semibold">
                          {dupCheck.is_duplicate
                            ? `知识库查重提醒：检测到与已有素材相似（最高相似度: ${Math.round(
                                dupCheck.max_score * 100,
                              )}%）`
                            : '查重通过：知识库中未检测到重复经历，属于全新优质素材！'}
                        </div>
                        {dupCheck.is_duplicate &&
                          dupCheck.similar_chunks.length > 0 && (
                            <div className="text-text-secondary text-[11px] pt-1">
                              已有相似素材：
                              <span className="font-mono text-text-primary">
                                {dupCheck.similar_chunks[0].source_file}
                              </span>
                              <div className="italic text-text-muted line-clamp-1 mt-0.5">
                                "{dupCheck.similar_chunks[0].chunk_text}"
                              </div>
                            </div>
                          )}
                      </div>
                    </div>
                  )}

                  {/* STAR 成果卡片 */}
                  <div className="p-5 rounded-xl bg-bg-secondary border border-border-subtle shadow-sm space-y-4">
                    <div className="flex items-center justify-between pb-3 border-b border-border-subtle">
                      <div>
                        <span className="text-xs font-mono px-2 py-0.5 rounded bg-brand-primary-muted text-brand-primary">
                          STAR 结构化资产
                        </span>
                        <h3 className="text-base font-bold text-text-primary mt-1">
                          {session.title}
                        </h3>
                      </div>
                      <span className="text-xs text-text-muted">
                        {starResult.summary}
                      </span>
                    </div>

                    {/* 技术栈标签 */}
                    {starResult.tech_stack &&
                      starResult.tech_stack.length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="text-xs text-text-muted">
                            技术标签:
                          </span>
                          {starResult.tech_stack.map((t, idx) => (
                            <span
                              key={idx}
                              className="px-2 py-0.5 text-[11px] font-mono rounded bg-bg-tertiary text-text-secondary border border-border-subtle"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      )}

                    {/* S-T-A-R 结构化详情 */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                      <div className="p-3 rounded-lg bg-bg-tertiary/60 border border-border-subtle">
                        <div className="font-semibold text-brand-primary mb-1">
                          S · 背景与目标
                        </div>
                        <p className="text-text-secondary leading-relaxed">
                          {starResult.situation}
                        </p>
                      </div>
                      <div className="p-3 rounded-lg bg-bg-tertiary/60 border border-border-subtle">
                        <div className="font-semibold text-brand-primary mb-1">
                          T · 核心职责与挑战
                        </div>
                        <p className="text-text-secondary leading-relaxed">
                          {starResult.task}
                        </p>
                      </div>
                      <div className="p-3 rounded-lg bg-bg-tertiary/60 border border-border-subtle">
                        <div className="font-semibold text-brand-primary mb-1">
                          A · 技术方案与动作
                        </div>
                        <p className="text-text-secondary leading-relaxed">
                          {starResult.action}
                        </p>
                      </div>
                      <div className="p-3 rounded-lg bg-bg-tertiary/60 border border-border-subtle">
                        <div className="font-semibold text-brand-primary mb-1">
                          R · 量化指标与成果
                        </div>
                        <p className="text-text-secondary leading-relaxed">
                          {starResult.result}
                        </p>
                      </div>
                    </div>

                    {/* ATS 高光 Bullet Points（支持在线微调） */}
                    <div className="space-y-2 pt-2 border-t border-border-subtle">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
                          <span>✨</span> ATS 推荐简历要点 (Bullet Points)
                        </label>
                        <span className="text-[11px] text-text-muted">
                          可点击文字直接编辑
                        </span>
                      </div>

                      <div className="space-y-2">
                        {starResult.bullet_points.map((bp, idx) => (
                          <div
                            key={idx}
                            className="p-3 rounded-lg bg-bg-tertiary border border-border-subtle hover:border-brand-primary/40 transition-colors text-xs leading-relaxed group relative"
                          >
                            {editingBulletIndex === idx ? (
                              <div className="space-y-1.5">
                                <textarea
                                  rows={3}
                                  value={bp}
                                  onChange={(e) =>
                                    handleUpdateBullet(idx, e.target.value)
                                  }
                                  className="w-full bg-bg-primary border border-brand-primary rounded p-2 text-xs text-text-primary focus:outline-none resize-none"
                                />
                                <button
                                  type="button"
                                  onClick={() => setEditingBulletIndex(null)}
                                  className="px-2.5 py-1 text-[11px] font-medium text-white bg-brand-primary rounded cursor-pointer border-none"
                                >
                                  完成修改
                                </button>
                              </div>
                            ) : (
                              <div
                                onClick={() => setEditingBulletIndex(idx)}
                                className="cursor-text text-text-primary"
                              >
                                <span className="text-brand-primary font-bold mr-1.5">
                                  •
                                </span>
                                {bp}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* 底部入库操作条 */}
                  {!commitSuccessMsg && (
                    <div className="flex items-center justify-between pt-2">
                      <button
                        type="button"
                        onClick={() => triggerSynthesize(session.id)}
                        disabled={synthesizing || committing}
                        className="px-4 py-2 text-xs text-text-secondary hover:text-text-primary rounded-lg border border-border-default hover:bg-bg-tertiary transition-colors cursor-pointer bg-transparent"
                      >
                        🔄 重新提炼
                      </button>

                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => {
                            setSession(null);
                            setStarResult(null);
                            void loadInitialData();
                          }}
                          className="px-3 py-2 text-xs text-text-muted hover:text-text-primary cursor-pointer border-none bg-transparent"
                        >
                          返回草稿
                        </button>
                        <button
                          type="button"
                          onClick={handleCommit}
                          disabled={committing || synthesizing}
                          className="px-5 py-2 rounded-lg text-sm font-medium text-white shadow transition-all hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer border-none flex items-center gap-2"
                          style={{
                            background:
                              'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
                          }}
                        >
                          {committing ? (
                            <>
                              <span className="animate-spin inline-block">
                                ⏳
                              </span>{' '}
                              正在沉淀入库...
                            </>
                          ) : (
                            '📥 确认沉淀入知识库'
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-12 text-center text-sm text-text-muted">
                  暂无提炼成果，请检查上一步回答。
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
