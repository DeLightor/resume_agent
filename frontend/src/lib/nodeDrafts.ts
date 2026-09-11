/** Per-node draft queues. No React/browser dependency so race handling is testable. */
export type DraftContent = Record<string, unknown>;
export type DraftStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error' | 'conflict';
export interface DraftNode { node_id: string; version: number; content_json?: DraftContent | null }
export interface DraftSnapshot {
  content: DraftContent;
  version: number;
  status: DraftStatus;
  error: string | null;
}
type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
interface Options {
  save: (id: string, content: DraftContent, version: number) => Promise<DraftNode>;
  load: (id: string) => Promise<DraftNode>;
  storage?: StorageLike;
  delay?: number;
  onSaved?: (node: DraftNode) => void;
}
interface Entry {
  snapshot: DraftSnapshot;
  dirty: boolean;
  revision: number;
  composing: boolean;
  timer?: ReturnType<typeof setTimeout>;
  saving?: Promise<boolean>;
  listeners: Set<() => void>;
}
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const prefix = 'resume-agent:node-draft:';
/** Compare JSON content rather than property insertion order. Only the root version is metadata. */
function sameContent(left: DraftContent, right: DraftContent): boolean {
  const normalize = (value: unknown, root = false): unknown => {
    if (Array.isArray(value)) return value.map(item => normalize(item));
    if (value && typeof value === 'object') {
      const object = value as Record<string, unknown>;
      return Object.fromEntries(Object.keys(object).sort()
        .filter(key => !(root && key === 'version'))
        .map(key => [key, normalize(object[key])]));
    }
    return value;
  };
  return JSON.stringify(normalize(left, true)) === JSON.stringify(normalize(right, true));
}
export class NodeDraftStore {
  private entries = new Map<string, Entry>();
  private options: Options;
  constructor(options: Options) { this.options = options; }

  ensure(node: DraftNode): void {
    if (this.entries.has(node.node_id)) return;
    let snapshot: DraftSnapshot = { content: copy(node.content_json ?? {}), version: node.version, status: 'idle', error: null };
    let dirty = false;
    try {
      const raw = this.options.storage?.getItem(prefix + node.node_id);
      if (raw) {
        const saved = JSON.parse(raw);
        if (Number.isInteger(saved.version) && saved.content && typeof saved.content === 'object' && !Array.isArray(saved.content)) {
          if (node.content_json !== undefined && node.version >= saved.version && sameContent(saved.content, node.content_json ?? {})) {
            // The server accepted a request before unload, but the browser never received its ACK.
            snapshot.status = 'saved';
            this.options.storage?.removeItem(prefix + node.node_id);
          } else {
            dirty = true;
            const conflict = saved.version !== node.version;
            snapshot = { content: saved.content, version: saved.version, status: conflict ? 'conflict' : 'pending', error: conflict ? '服务端内容已更新，本地草稿已保留。请复制需要的内容后重新加载。' : null };
          }
        }
      }
    } catch { /* A malformed draft must never overwrite a valid server document. */ }
    this.entries.set(node.node_id, { snapshot, dirty, revision: 0, composing: false, listeners: new Set() });
  }

  receive(node: DraftNode): void {
    this.ensure(node);
    const entry = this.entries.get(node.node_id)!;
    if (node.version < entry.snapshot.version || entry.saving || node.content_json === undefined) return;
    if (entry.dirty && sameContent(entry.snapshot.content, node.content_json ?? {})) {
      clearTimeout(entry.timer);
      entry.dirty = false;
      this.publish(entry, { content: copy(node.content_json ?? {}), version: node.version, status: 'saved', error: null });
      this.persist(node.node_id, entry);
      return;
    }
    if (node.version === entry.snapshot.version && (entry.dirty || JSON.stringify(node.content_json ?? {}) === JSON.stringify(entry.snapshot.content))) return;
    if (entry.dirty) {
      this.publish(entry, { status: 'conflict', error: '服务端内容已更新，本地草稿已保留。请复制需要的内容后重新加载。' });
    } else {
      this.publish(entry, { content: copy(node.content_json ?? {}), version: node.version, status: 'idle', error: null });
    }
  }

  get(id: string): DraftSnapshot { return this.entries.get(id)!.snapshot; }
  subscribe(id: string, listener: () => void): () => void {
    const entry = this.entries.get(id)!;
    entry.listeners.add(listener);
    return () => { entry.listeners.delete(listener); };
  }
  private publish(entry: Entry, change: Partial<DraftSnapshot>): void {
    entry.snapshot = { ...entry.snapshot, ...change };
    entry.listeners.forEach(listener => listener());
  }
  private persist(id: string, entry: Entry): void {
    try {
      if (entry.dirty) this.options.storage?.setItem(prefix + id, JSON.stringify({ version: entry.snapshot.version, content: entry.snapshot.content }));
      else this.options.storage?.removeItem(prefix + id);
    } catch {
      this.publish(entry, { error: '浏览器无法保留草稿，请勿关闭页面；联网保存成功后再离开。' });
    }
  }
  private schedule(id: string, entry: Entry): void {
    clearTimeout(entry.timer);
    if (entry.composing || entry.snapshot.status === 'conflict') return;
    entry.timer = setTimeout(() => { void this.flush(id); }, this.options.delay ?? 800);
  }
  edit(id: string, mutator: (content: DraftContent) => void): void {
    const entry = this.entries.get(id)!;
    const content = copy(entry.snapshot.content);
    mutator(content);
    if (JSON.stringify(content) === JSON.stringify(entry.snapshot.content)) return;
    entry.dirty = true;
    entry.revision++;
    this.publish(entry, { content, status: entry.snapshot.status === 'conflict' ? 'conflict' : 'pending' });
    this.persist(id, entry);
    this.schedule(id, entry);
  }
  setComposing(id: string, composing: boolean): void {
    const entry = this.entries.get(id);
    if (!entry) return;
    entry.composing = composing;
    if (composing) clearTimeout(entry.timer);
    else if (entry.dirty) this.schedule(id, entry);
  }
  flush(id: string): Promise<boolean> {
    const entry = this.entries.get(id);
    if (!entry) return Promise.resolve(true);
    clearTimeout(entry.timer);
    if (entry.saving) return entry.saving;
    if (entry.snapshot.status === 'conflict' || entry.composing) return Promise.resolve(false);
    if (!entry.dirty) return Promise.resolve(true);
    const run = async (): Promise<boolean> => {
      while (entry.dirty && !entry.composing) {
        const revision = entry.revision;
        const content = copy(entry.snapshot.content);
        const version = entry.snapshot.version;
        this.publish(entry, { status: 'saving', error: null });
        try {
          const result = await this.options.save(id, content, version);
          const unchanged = entry.revision === revision;
          entry.dirty = !unchanged;
          this.publish(entry, {
            content: unchanged ? copy(result.content_json ?? content) : { ...entry.snapshot.content, version: result.version },
            version: result.version,
            status: unchanged ? 'saved' : 'pending',
            error: null,
          });
          this.persist(id, entry);
          this.options.onSaved?.(result);
        } catch (error) {
          const message = error instanceof Error ? error.message : '保存失败';
          const conflict = (typeof error === 'object' && error !== null && 'status' in error && error.status === 409) || /409|conflict|版本冲突/i.test(message);
          this.publish(entry, { status: conflict ? 'conflict' : 'error', error: conflict ? '保存冲突：服务端已有新版本，本地草稿已保留。请复制需要的内容后重新加载。' : `保存失败，草稿已保留：${message}` });
          this.persist(id, entry);
          clearTimeout(entry.timer);
          return false;
        }
      }
      return !entry.dirty;
    };
    entry.saving = run().finally(() => { entry.saving = undefined; });
    return entry.saving;
  }
  async flushAll(): Promise<boolean> {
    const results = await Promise.all([...this.entries.keys()].map(id => {
      this.setComposing(id, false);
      return this.flush(id);
    }));
    return results.every(Boolean);
  }
  async reload(id: string): Promise<void> {
    const entry = this.entries.get(id)!;
    clearTimeout(entry.timer);
    if (entry.saving) await entry.saving;
    const revision = entry.revision;
    try {
      const node = await this.options.load(id);
      if (revision !== entry.revision) return; // Do not discard edits typed while GET was in flight.
      entry.dirty = false;
      this.publish(entry, { content: copy(node.content_json ?? {}), version: node.version, status: 'idle', error: null });
      this.persist(id, entry);
    } catch (error) {
      this.publish(entry, { error: error instanceof Error ? error.message : '重新加载失败，草稿仍保留。' });
    }
  }
}
