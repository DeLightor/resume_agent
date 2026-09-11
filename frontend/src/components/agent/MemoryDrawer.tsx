// frontend/src/components/agent/MemoryDrawer.tsx
// Agent 长期记忆管理抽屉（US-35 agent-long-term-memory）

import { useEffect, useState } from 'react';
import type { AgentMemory, AgentMemoryType } from '@/types/agent';
import {
  createMemory,
  deleteMemory,
  getMemories,
  updateMemory,
} from '@/lib/api';

interface MemoryDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onMemoryChanged?: () => void;
}

const TYPE_CONFIG: Record<
  AgentMemoryType,
  { label: string; tagCls: string; badgeCls: string; placeholder: string }
> = {
  preference: {
    label: '偏好',
    tagCls: 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800',
    badgeCls: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
    placeholder: '例如：项目经历中重点突出性能优化与指标量化...',
  },
  correction: {
    label: '纠偏',
    tagCls: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:border-rose-800',
    badgeCls: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
    placeholder: '例如：技能清单禁止出现「精通」，统一写「熟练」...',
  },
  style_sample: {
    label: '风格',
    tagCls: 'bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800',
    badgeCls: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
    placeholder: '例如：项目描述统一采用 STAR 结构（情境-任务-行动-结果）...',
  },
};

export default function MemoryDrawer({
  isOpen,
  onClose,
  onMemoryChanged,
}: MemoryDrawerProps) {
  const [memories, setMemories] = useState<AgentMemory[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 筛选与搜索
  const [selectedType, setSelectedType] = useState<AgentMemoryType | 'all'>('all');
  const [activeOnly, setActiveOnly] = useState(false);

  // 新增表单状态
  const [isAdding, setIsAdding] = useState(false);
  const [newType, setNewType] = useState<AgentMemoryType>('preference');
  const [newContent, setNewContent] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // 编辑状态
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');

  const fetchMemories = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMemories(false);
      setMemories(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      void fetchMemories();
      setIsAdding(false);
      setEditingId(null);
    }
  }, [isOpen]);

  const handleToggleActive = async (memory: AgentMemory) => {
    const nextActive = !memory.active;
    // 乐观更新
    setMemories((prev) =>
      prev.map((m) => (m.id === memory.id ? { ...m, active: nextActive } : m)),
    );
    try {
      await updateMemory(memory.id, { active: nextActive });
      onMemoryChanged?.();
    } catch (err) {
      // 失败回滚
      setMemories((prev) =>
        prev.map((m) => (m.id === memory.id ? { ...m, active: memory.active } : m)),
      );
      setError(err instanceof Error ? err.message : '更新状态失败');
    }
  };

  const handleCreate = async () => {
    if (!newContent.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createMemory({
        content: newContent.trim(),
        type: newType,
        source: 'manual',
      });
      setMemories((prev) => [created, ...prev]);
      setNewContent('');
      setIsAdding(false);
      onMemoryChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建记忆失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveEdit = async (id: string) => {
    if (!editContent.trim()) return;
    try {
      const updated = await updateMemory(id, { content: editContent.trim() });
      setMemories((prev) => prev.map((m) => (m.id === id ? updated : m)));
      setEditingId(null);
      onMemoryChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('确定要删除这条长期记忆规则吗？删除后 Agent 将不再遵守。')) {
      return;
    }
    try {
      await deleteMemory(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      onMemoryChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  if (!isOpen) return null;

  const filteredMemories = memories.filter((m) => {
    if (activeOnly && !m.active) return false;
    if (selectedType !== 'all' && m.type !== selectedType) return false;
    return true;
  });

  const activeCount = memories.filter((m) => m.active).length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-xs transition-opacity duration-200">
      {/* 遮罩点击关闭 */}
      <div className="absolute inset-0 cursor-pointer" onClick={onClose} />

      {/* 抽屉主面板 */}
      <div className="relative w-full max-w-lg h-full bg-bg-primary border-l border-border-default shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-200">
        {/* 顶部标题栏 */}
        <div className="p-4 border-b border-border-default flex items-center justify-between bg-bg-secondary shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-xl">🧠</span>
            <div>
              <h3 className="text-base font-semibold text-text-primary flex items-center gap-2">
                Agent 长期记忆
                <span className="text-xs px-2 py-0.5 rounded-full font-normal bg-brand-primary/10 text-brand-primary">
                  生效中 {activeCount} / 共 {memories.length}
                </span>
              </h3>
              <p className="text-xs text-text-muted mt-0.5">
                跨会话持久化生效的偏好、纠偏红线与风格习惯
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-hover border-none bg-transparent cursor-pointer transition-colors"
            title="关闭 (Esc)"
          >
            ✕
          </button>
        </div>

        {/* 提示与操作条 */}
        <div className="p-3 border-b border-border-default bg-bg-primary shrink-0 flex flex-col gap-2">
          {error && (
            <div className="px-3 py-1.5 rounded bg-rose-50 dark:bg-rose-900/30 text-rose-600 dark:text-rose-300 text-xs flex items-center justify-between">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => setError(null)}
                className="text-rose-500 hover:text-rose-700 bg-transparent border-none cursor-pointer"
              >
                ✕
              </button>
            </div>
          )}

          <div className="flex items-center justify-between gap-2">
            {/* 分类切换 Tab */}
            <div className="flex items-center gap-1 bg-bg-secondary p-0.5 rounded-lg border border-border-default text-xs">
              {(['all', 'preference', 'correction', 'style_sample'] as const).map(
                (type) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setSelectedType(type)}
                    className={`px-2.5 py-1 rounded-md transition-colors border-none cursor-pointer ${
                      selectedType === type
                        ? 'bg-bg-primary text-text-primary font-medium shadow-xs'
                        : 'text-text-secondary hover:text-text-primary bg-transparent'
                    }`}
                  >
                    {type === 'all' ? '全部' : TYPE_CONFIG[type].label}
                  </button>
                ),
              )}
            </div>

            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1 text-xs text-text-secondary cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={activeOnly}
                  onChange={(e) => setActiveOnly(e.target.checked)}
                  className="rounded border-border-default text-brand-primary"
                />
                仅生效中
              </label>

              <button
                type="button"
                onClick={() => setIsAdding((v) => !v)}
                className="px-2.5 py-1 rounded text-xs bg-brand-primary text-white border-none cursor-pointer hover:bg-brand-primary-hover font-medium transition-colors flex items-center gap-1"
              >
                {isAdding ? '收起' : '+ 添加规则'}
              </button>
            </div>
          </div>

          {/* 新增规则抽屉内嵌表单 */}
          {isAdding && (
            <div className="mt-2 p-3 rounded-lg border border-brand-primary/30 bg-brand-primary/5 flex flex-col gap-2.5 animate-in fade-in duration-150">
              <div className="flex items-center gap-2 text-xs">
                <span className="text-text-secondary font-medium">规则类型：</span>
                {(['preference', 'correction', 'style_sample'] as const).map((t) => (
                  <label
                    key={t}
                    className={`flex items-center gap-1 px-2 py-0.5 rounded cursor-pointer border text-xs transition-colors ${
                      newType === t
                        ? TYPE_CONFIG[t].tagCls + ' font-medium'
                        : 'border-border-default text-text-secondary bg-bg-primary'
                    }`}
                  >
                    <input
                      type="radio"
                      name="memory_type"
                      checked={newType === t}
                      onChange={() => setNewType(t)}
                      className="sr-only"
                    />
                    {TYPE_CONFIG[t].label}
                  </label>
                ))}
              </div>

              <textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder={TYPE_CONFIG[newType].placeholder}
                rows={2}
                className="w-full text-xs p-2 rounded border border-border-default bg-bg-primary text-text-primary focus:outline-none focus:border-brand-primary resize-none"
              />

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setIsAdding(false);
                    setNewContent('');
                  }}
                  className="px-2.5 py-1 rounded text-xs text-text-secondary hover:bg-bg-hover border border-border-default bg-bg-primary cursor-pointer"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={() => void handleCreate()}
                  disabled={submitting || !newContent.trim()}
                  className="px-3 py-1 rounded text-xs bg-brand-primary text-white border-none cursor-pointer hover:bg-brand-primary-hover disabled:opacity-50 font-medium"
                >
                  {submitting ? '保存中...' : '保存记忆'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* 记忆规则列表 */}
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2.5">
          {loading && (
            <div className="p-8 text-center text-xs text-text-muted">
              加载长期记忆中...
            </div>
          )}

          {!loading && filteredMemories.length === 0 && (
            <div className="p-10 text-center flex flex-col items-center justify-center gap-2 text-text-muted">
              <span className="text-3xl">📝</span>
              <p className="text-sm font-medium text-text-secondary">
                {activeOnly || selectedType !== 'all'
                  ? '没有符合筛选条件的记忆规则'
                  : '暂无沉淀的记忆规则'}
              </p>
              <p className="text-xs max-w-xs text-center">
                在对话中输入「请记住：...」或「以后都不要...」，AI 将自动提炼为长期规则；也可点击右上角手动录入。
              </p>
            </div>
          )}

          {!loading &&
            filteredMemories.map((mem) => {
              const cfg = TYPE_CONFIG[mem.type] ?? TYPE_CONFIG.preference;
              const isEditing = editingId === mem.id;

              return (
                <div
                  key={mem.id}
                  className={`p-3 rounded-lg border transition-all duration-200 ${
                    mem.active
                      ? 'bg-bg-primary border-border-default shadow-xs'
                      : 'bg-bg-secondary/60 border-border-default/60 opacity-60'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      {/* 类型标签 */}
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${cfg.tagCls}`}
                      >
                        {cfg.label}
                      </span>
                      {/* 来源标记 */}
                      <span className="text-[10px] text-text-muted">
                        {mem.source === 'manual' ? '✍️ 手动录入' : '🤖 对话提炼'}
                      </span>
                    </div>

                    {/* 右侧：生效开关与操作 */}
                    <div className="flex items-center gap-2">
                      <label
                        className="flex items-center gap-1 text-[11px] text-text-secondary cursor-pointer select-none"
                        title={mem.active ? '点击禁用该规则' : '点击启用该规则'}
                      >
                        <input
                          type="checkbox"
                          checked={mem.active}
                          onChange={() => void handleToggleActive(mem)}
                          className="w-3.5 h-3.5 text-brand-primary rounded cursor-pointer"
                        />
                        <span>{mem.active ? '生效' : '已禁'}</span>
                      </label>

                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(mem.id);
                          setEditContent(mem.content);
                        }}
                        className="text-text-muted hover:text-brand-primary text-xs p-1 rounded hover:bg-bg-hover border-none bg-transparent cursor-pointer"
                        title="编辑内容"
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(mem.id)}
                        className="text-text-muted hover:text-rose-600 text-xs p-1 rounded hover:bg-bg-hover border-none bg-transparent cursor-pointer"
                        title="删除规则"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>

                  {/* 规则正文 */}
                  {isEditing ? (
                    <div className="mt-2 flex flex-col gap-2">
                      <textarea
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        className="w-full text-xs p-2 rounded border border-brand-primary bg-bg-primary text-text-primary focus:outline-none resize-none"
                        rows={2}
                      />
                      <div className="flex justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="px-2 py-0.5 rounded text-[11px] text-text-secondary hover:bg-bg-hover border border-border-default bg-bg-primary cursor-pointer"
                        >
                          取消
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleSaveEdit(mem.id)}
                          className="px-2.5 py-0.5 rounded text-[11px] bg-brand-primary text-white border-none cursor-pointer hover:bg-brand-primary-hover font-medium"
                        >
                          保存
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2 text-xs text-text-primary leading-relaxed break-words font-medium">
                      {mem.content}
                    </div>
                  )}

                  {/* 底部时间戳 */}
                  {mem.updated_at && (
                    <div className="mt-2 text-[10px] text-text-muted">
                      更新于{' '}
                      {new Date(mem.updated_at).toLocaleString('zh-CN', {
                        month: 'numeric',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </div>
                  )}
                </div>
              );
            })}
        </div>

        {/* 底部帮助说明 */}
        <div className="p-3 border-t border-border-default bg-bg-secondary text-[11px] text-text-muted shrink-0 leading-tight">
          💡 <strong>机制提示</strong>：生效中的规则会自动挂载到 Agent
          思考与审查阶段（Top-8 预算限制）。如遇特定场景不需要某条偏好，直接取消勾选即可暂时屏蔽。
        </div>
      </div>
    </div>
  );
}
