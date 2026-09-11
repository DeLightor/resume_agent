import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { getNode, updateNode } from '@/lib/api';
import { NodeDraftStore, type DraftContent, type DraftSnapshot } from '@/lib/nodeDrafts';
import type { ResumeNode } from '@/types/tree';

function asDraftNode(node: ResumeNode) {
  return { ...node, version: node.version ?? Number(node.content_json?.version ?? 0) };
}

let storage: Storage | undefined;
try { storage = window.localStorage; } catch { /* Browser may disable local storage. */ }
export const nodeDraftStore = new NodeDraftStore({
  storage,
  save: async (id, content, version) => asDraftNode(await updateNode(id, { content_json: content, expected_version: version })),
  load: async id => asDraftNode(await getNode(id)),
  onSaved: node => window.dispatchEvent(new CustomEvent('node-draft-saved', { detail: node })),
});
// Edits are persisted synchronously. Network flush is best effort when the browser exits.
window.addEventListener('pagehide', () => { void nodeDraftStore.flushAll(); });
window.addEventListener('beforeunload', () => { void nodeDraftStore.flushAll(); });
const empty: DraftSnapshot = { content: {}, version: 0, status: 'idle', error: null };

/** Shared interface for preview, history, personal info, and section order.
 * status: idle | pending | saving | saved | error | conflict.
 * edit mutates a cloned full content document; flush resolves false on conflict/failure.
 * reload explicitly discards the local draft only after loading the server successfully.
 */
export function useNodeDraft(node: ResumeNode | null) {
  const id = node?.node_id ?? null;
  if (node) nodeDraftStore.ensure(asDraftNode(node));
  const subscribe = useCallback((listener: () => void) => id ? nodeDraftStore.subscribe(id, listener) : () => {}, [id]);
  const snapshot = useCallback(() => id ? nodeDraftStore.get(id) : empty, [id]);
  const draft = useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(() => { if (node) nodeDraftStore.receive(asDraftNode(node)); }, [node]);
  useEffect(() => {
    if (id && nodeDraftStore.get(id).status === 'pending') void nodeDraftStore.flush(id);
  }, [id]);
  useEffect(() => () => {
    if (id) {
      nodeDraftStore.setComposing(id, false);
      void nodeDraftStore.flush(id);
    }
  }, [id]);
  const edit = useCallback((mutator: (content: DraftContent) => void) => {
    if (id) nodeDraftStore.edit(id, mutator);
  }, [id]);
  const flush = useCallback(() => id ? nodeDraftStore.flush(id) : Promise.resolve(true), [id]);
  const reload = useCallback(() => id ? nodeDraftStore.reload(id) : Promise.resolve(), [id]);
  const setComposing = useCallback((value: boolean) => { if (id) nodeDraftStore.setComposing(id, value); }, [id]);
  return { ...draft, content: id ? draft.content : null, edit, flush, reload, setComposing };
}

/** For side panels supplied with just an ID. Ignore responses from previous selections. */
export function useNodeDraftById(nodeId: string | null) {
  const [node, setNode] = useState<ResumeNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const loadGeneration = useRef(0);
  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    if (!nodeId) { setNode(null); setLoading(false); setLoadError(null); return; }
    setLoading(true);
    setLoadError(null);
    try {
      const result = await getNode(nodeId);
      if (generation === loadGeneration.current) setNode(result);
    } catch (error) {
      if (generation === loadGeneration.current) setLoadError(error instanceof Error ? error.message : '加载节点失败');
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  }, [nodeId]);
  useEffect(() => {
    void load();
    return () => { loadGeneration.current++; };
  }, [load]);
  const draft = useNodeDraft(node?.node_id === nodeId ? node : null);
  return { ...draft, loading: loading || (!!nodeId && node?.node_id !== nodeId && !loadError), loadError, retryLoad: load };
}
