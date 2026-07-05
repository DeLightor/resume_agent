// frontend/src/components/tree/CreateNodeModal.tsx
// 新建节点弹窗：支持新建方向分支（parent=master）或公司节点（parent=branch）

import { useState } from 'react';
import { createNode } from '@/lib/api';
import type { CreateNodeRequest, ResumeNode } from '@/types/tree';

interface CreateNodeModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  /** 可选父节点（用于推导 master / branch 选项） */
  parentOptions: ResumeNode[];
}

type FormType = 'branch' | 'company';

const INPUT_CLASS =
  'w-full bg-bg-tertiary border border-border-default rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand-primary transition-colors';

export default function CreateNodeModal({
  open,
  onClose,
  onCreated,
  parentOptions,
}: CreateNodeModalProps) {
  const [formType, setFormType] = useState<FormType>('branch');
  const [direction, setDirection] = useState('');
  const [parentBranchId, setParentBranchId] = useState('');
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const branchOptions = parentOptions.filter((n) => n.node_type === 'branch');
  const masterNode = parentOptions.find((n) => n.node_type === 'master');

  const reset = () => {
    setFormType('branch');
    setDirection('');
    setParentBranchId('');
    setCompany('');
    setRole('');
    setError(null);
    setSubmitting(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      let req: CreateNodeRequest;
      if (formType === 'branch') {
        const trimmed = direction.trim();
        if (!trimmed) {
          setError('请输入方向名称');
          setSubmitting(false);
          return;
        }
        req = {
          parent_id: masterNode?.node_id ?? 'master',
          node_type: 'branch',
          title: trimmed,
          direction: trimmed,
        };
      } else {
        const trimmedCompany = company.trim();
        const trimmedRole = role.trim();
        const parentId = parentBranchId || branchOptions[0]?.node_id;
        if (!parentId) {
          setError('请选择所属分支');
          setSubmitting(false);
          return;
        }
        if (!trimmedCompany) {
          setError('请输入公司名称');
          setSubmitting(false);
          return;
        }
        const title = trimmedRole
          ? `${trimmedCompany} ${trimmedRole}`
          : trimmedCompany;
        req = {
          parent_id: parentId,
          node_type: 'company',
          title,
          company: trimmedCompany,
        };
      }
      await createNode(req);
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建节点失败');
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={handleClose}
    >
      <div
        className="w-[420px] max-w-[90vw] bg-bg-secondary rounded-lg shadow-lg border border-border-subtle p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-text-primary">新建节点</h3>
          <button
            type="button"
            onClick={handleClose}
            aria-label="关闭"
            className="text-text-muted hover:text-text-primary transition-colors cursor-pointer border-none bg-transparent text-lg leading-none p-0"
          >
            ×
          </button>
        </div>

        {/* 节点类型切换 */}
        <div className="flex gap-0.5 bg-bg-tertiary rounded-md p-0.5 mb-4">
          {(['branch', 'company'] as FormType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setFormType(t)}
              className={`flex-1 px-3 py-1.5 rounded-sm text-xs transition-all border-none cursor-pointer font-body ${
                formType === t
                  ? 'bg-bg-elevated text-text-primary font-medium shadow-sm'
                  : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              {t === 'branch' ? '方向分支' : '公司节点'}
            </button>
          ))}
        </div>

        {/* 表单字段 */}
        <div className="flex flex-col gap-3">
          {formType === 'branch' ? (
            <div>
              <label className="block text-xs text-text-secondary mb-1.5">
                方向名称
              </label>
              <input
                type="text"
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
                placeholder="如：安全、算法、后端"
                className={INPUT_CLASS}
                autoFocus
              />
              <p className="text-xs text-text-muted mt-1.5">
                将以 master 为主干创建方向分支
              </p>
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs text-text-secondary mb-1.5">
                  所属分支
                </label>
                <select
                  value={parentBranchId}
                  onChange={(e) => setParentBranchId(e.target.value)}
                  className={INPUT_CLASS}
                >
                  {branchOptions.length === 0 && (
                    <option value="">暂无可选分支</option>
                  )}
                  {branchOptions.map((b) => (
                    <option key={b.node_id} value={b.node_id}>
                      {b.title}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-text-secondary mb-1.5">
                  公司名称
                </label>
                <input
                  type="text"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  placeholder="如：Tencent、ByteDance"
                  className={INPUT_CLASS}
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-xs text-text-secondary mb-1.5">
                  岗位（可选）
                </label>
                <input
                  type="text"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="如：安全研究员"
                  className={INPUT_CLASS}
                />
              </div>
            </>
          )}

          {error && <div className="text-xs text-error">{error}</div>}
        </div>

        {/* 底部操作 */}
        <div className="flex justify-end gap-2 mt-5">
          <button
            type="button"
            onClick={handleClose}
            className="px-4 py-2 text-sm text-text-secondary bg-transparent border border-border-default rounded-md cursor-pointer hover:bg-bg-hover transition-colors"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 text-sm text-white border-none rounded-md cursor-pointer transition-all hover:brightness-110 disabled:opacity-60 disabled:cursor-not-allowed"
            style={{
              background:
                'linear-gradient(135deg, var(--color-accent-gradient-start), var(--color-accent-gradient-end))',
            }}
          >
            {submitting ? '创建中...' : '创建'}
          </button>
        </div>
      </div>
    </div>
  );
}
