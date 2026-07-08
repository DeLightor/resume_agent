// frontend/src/components/completeness/CompletenessBar.tsx
// US-15: 完整性检测评分条 + 缺失清单

import { useEffect, useState, useCallback } from 'react';
import { checkCompleteness } from '@/lib/api';

interface CompletenessCheck {
  field: string;
  status: 'ok' | 'missing' | 'weak';
  message?: string;
  count?: number;
}

interface CompletenessBarProps {
  nodeId: string | null;
  /** 完整性检测更新触发器（内容变化时递增） */
  refreshKey: number;
  /** 点击清单项跳转 */
  onJumpToSection?: (field: string) => void;
}

export default function CompletenessBar({
  nodeId,
  refreshKey,
  onJumpToSection,
}: CompletenessBarProps) {
  const [score, setScore] = useState<number | null>(null);
  const [checks, setChecks] = useState<CompletenessCheck[]>([]);
  const [collapsed, setCollapsed] = useState(false);

  const runCheck = useCallback(async () => {
    if (!nodeId) {
      setScore(null);
      setChecks([]);
      return;
    }
    try {
      const result = await checkCompleteness(nodeId);
      setScore(result.score);
      setChecks(result.checks as unknown as CompletenessCheck[]);
    } catch {
      setScore(null);
      setChecks([]);
    }
  }, [nodeId]);

  useEffect(() => {
    runCheck();
  }, [runCheck, refreshKey]);

  if (score === null) return null;

  const problemChecks = checks.filter((c) => c.status !== 'ok');
  const scoreColor =
    score >= 80 ? '#16a34a' : score >= 50 ? '#f59e0b' : '#ef4444';

  return (
    <div className="border-b border-border-subtle bg-bg-elevated">
      {/* 评分条 */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-3 px-4 py-2 hover:bg-bg-tertiary transition-colors"
      >
        <div className="flex items-center gap-2 flex-1">
          <span className="text-xs font-semibold text-text-primary">完整度</span>
          <div className="flex-1 h-1.5 rounded-full bg-bg-tertiary overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${score}%`, backgroundColor: scoreColor }}
            />
          </div>
          <span
            className="text-xs font-bold tabular-nums"
            style={{ color: scoreColor }}
          >
            {score}
          </span>
        </div>
        {problemChecks.length > 0 && (
          <span className="text-[10px] text-text-muted">
            {problemChecks.length} 项待完善
          </span>
        )}
        <svg
          width="10"
          height="10"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`text-text-muted transition-transform ${collapsed ? '' : 'rotate-90'}`}
        >
          <path d="M6 4l4 4-4 4" />
        </svg>
      </button>

      {/* 问题清单 */}
      {!collapsed && problemChecks.length > 0 && (
        <div className="px-4 pb-3 space-y-1">
          {problemChecks.map((check) => (
            <button
              key={check.field}
              onClick={() => onJumpToSection?.(check.field)}
              className="flex items-center gap-2 w-full px-2 py-1 rounded hover:bg-bg-tertiary transition-colors text-left"
            >
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  check.status === 'missing' ? 'bg-error' : 'bg-warning'
                }`}
              />
              <span className="text-xs text-text-secondary flex-1">
                {check.message || check.field}
              </span>
              <span className="text-[10px] text-text-muted">
                {check.status === 'missing' ? '缺失' : '不足'}
              </span>
            </button>
          ))}
        </div>
      )}

      {!collapsed && problemChecks.length === 0 && (
        <div className="px-4 pb-2">
          <span className="text-xs text-success">✓ 所有信息完整</span>
        </div>
      )}
    </div>
  );
}
