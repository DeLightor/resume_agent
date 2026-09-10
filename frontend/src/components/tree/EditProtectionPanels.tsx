import { useCallback, useEffect, useRef, useState } from 'react';

import {
  getNodeHistory,
  getTrash,
  moveNodeHistory,
  restoreNode,
  type NodeHistory,
  type TrashItem,
} from '@/lib/api';
import { nodeDraftStore } from '@/hooks/useNodeDraft';
import type { ResumeNode } from '@/types/tree';

const buttonClass = 'min-h-11 rounded-md border border-border-default px-3 py-2 text-xs text-text-secondary hover:bg-bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-primary disabled:cursor-not-allowed disabled:opacity-40';

function message(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后重试';
}

/** SQLite dates are UTC even when they do not include a timezone suffix. */
function historySummary(value: string): string {
  const labels: Record<string, string> = { personal_info: '个人信息', contact: '联系方式', name: '姓名', gender: '性别', birth_date: '出生年月', phone: '电话', email: '邮箱', location: '所在城市', job_intention: '求职意向', education: '教育背景', summary: '自我评价', experience: '工作经历', projects: '项目经历', skills: '技能总结', section_order: '段落顺序', avatar: '头像' };
  if (!/^(更新|修改)\s/.test(value)) return value;
  return '修改 ' + value.replace(/^(更新|修改)\s*/, '').split('、').map(path => path.split('.').map(part => labels[part] ?? part).join(' / ')).join('、');
}

function dateLabel(value: string): string {
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value.replace(' ', 'T')}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN');
}

export function HistoryPanel({ node, onChanged, beforeAction }: {
  node: ResumeNode;
  onChanged: (node: ResumeNode) => void;
  beforeAction: () => Promise<boolean>;
}) {
  const [history, setHistory] = useState<NodeHistory | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const activeId = useRef(node.node_id);
  const actionLock = useRef(false);
  activeId.current = node.node_id;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setHistory(null);
    getNodeHistory(node.node_id)
      .then((result) => { if (!cancelled) setHistory(result); })
      .catch((reason: unknown) => { if (!cancelled) setError(message(reason)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [node.node_id, node.version, refresh]);

  useEffect(() => { setError(''); }, [node.node_id]);

  async function move(direction: 'undo' | 'redo') {
    if (actionLock.current) return;
    const id = node.node_id;
    actionLock.current = true;
    setBusy(true);
    setError('');
    try {
      if (!await beforeAction()) {
        if (activeId.current === id) setError('当前草稿尚未保存，请先处理保存错误再操作历史。');
        return;
      }
      if (activeId.current !== id) return;
      // Only use the revision this editor has actually seen or saved.
      const updated = await moveNodeHistory(id, direction, nodeDraftStore.get(id).version);
      if (activeId.current === id) {
        onChanged(updated);
        setRefresh((value) => value + 1);
      }
    } catch (reason) {
      if (activeId.current === id) setError(message(reason));
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }

  return (
    <section aria-label="编辑历史" className="rounded-lg border border-border-subtle bg-bg-secondary p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-text-primary">编辑历史</h3>
        <div className="flex gap-2">
          <button type="button" className={buttonClass} disabled={busy || loading || !history?.can_undo} onClick={() => void move('undo')}>撤销</button>
          <button type="button" className={buttonClass} disabled={busy || loading || !history?.can_redo} onClick={() => void move('redo')}>重做</button>
        </div>
      </div>
      <p className="mt-2 text-xs text-text-muted">保留最近 20 条记录。撤销后再次编辑会清除后续重做记录。</p>
      {error && <div role="alert" className="mt-2 text-xs text-error">
        <p>{error}</p>
        <button type="button" className={`${buttonClass} mt-2`} disabled={busy || loading} onClick={() => { setError(''); setRefresh((value) => value + 1); }}>刷新历史</button>
      </div>}
      {(loading || busy) && <p role="status" className="mt-2 text-xs text-text-muted">{busy ? '正在更新节点…' : '正在加载历史…'}</p>}
      {!loading && history && history.entries.length === 0 && <p className="mt-3 text-xs text-text-muted">尚无编辑记录</p>}
      {!loading && history && history.entries.length > 0 && <ol className="mt-3 max-h-48 space-y-2 overflow-y-auto">
        {[...history.entries].reverse().map((entry) => <li key={entry.id} className="border-t border-border-subtle pt-2 text-xs">
          <p className="break-words text-text-secondary">{historySummary(entry.summary)}</p>
          <time className="mt-1 block text-text-muted">{dateLabel(entry.created_at)}</time>
        </li>)}
      </ol>}
    </section>
  );
}

export function TrashPanel({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState<string | null>(null);
  const [error, setError] = useState('');
  const mounted = useRef(false);
  const requestId = useRef(0);
  const actionLock = useRef(false);

  const reload = useCallback(async () => {
    const request = ++requestId.current;
    setLoading(true);
    try {
      const result = await getTrash();
      if (mounted.current && request === requestId.current) setItems(result.items);
    } catch (reason) {
      if (mounted.current && request === requestId.current) setError(message(reason));
    } finally {
      if (mounted.current && request === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void reload();
    return () => { mounted.current = false; requestId.current += 1; };
  }, [reload]);

  async function restore(id: string) {
    if (actionLock.current) return;
    actionLock.current = true;
    setRestoring(id);
    setError('');
    try {
      await restoreNode(id);
      if (mounted.current) {
        onChanged();
        await reload();
      }
    } catch (reason) {
      if (mounted.current) setError(message(reason));
    } finally {
      actionLock.current = false;
      if (mounted.current) setRestoring(null);
    }
  }

  return (
    <section aria-label="回收站" className="rounded-lg border border-border-subtle bg-bg-secondary p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-text-primary">回收站</h3>
        <button type="button" className={buttonClass} disabled={loading || restoring !== null} onClick={() => { setError(''); void reload(); }}>刷新</button>
      </div>
      <p className="mt-2 text-xs text-text-muted">删除后 30 天内可恢复，随节点一起删除的子节点也会恢复。</p>
      {error && <p role="alert" className="mt-2 text-xs text-error">{error} 可刷新列表后重试。</p>}
      {loading && <p role="status" className="mt-3 text-xs text-text-muted">正在加载回收站…</p>}
      {!loading && items.length === 0 && <p className="mt-3 text-xs text-text-muted">暂无可恢复的节点</p>}
      {!loading && items.length > 0 && <ul className="mt-3 max-h-64 space-y-3 overflow-y-auto">
        {items.map((item) => <li key={item.node_id} className="flex items-start justify-between gap-3 border-t border-border-subtle pt-3">
          <div className="min-w-0 text-xs">
            <p className="break-words font-medium text-text-secondary">{item.title}</p>
            <p className="mt-1 text-text-muted">删除于 {dateLabel(item.deleted_at)}</p>
            <p className="mt-1 text-text-muted">恢复期限 {dateLabel(item.expires_at)}</p>
          </div>
          <button type="button" aria-label={`恢复 ${item.title}`} className={`${buttonClass} shrink-0`} disabled={restoring !== null} onClick={() => void restore(item.node_id)}>
            {restoring === item.node_id ? '恢复中…' : '恢复'}
          </button>
        </li>)}
      </ul>}
    </section>
  );
}
