import test from 'node:test';
import assert from 'node:assert/strict';
import { NodeDraftStore } from '../src/lib/nodeDrafts.ts';

const node = (version = 0, content = { name: 'original' }) => ({ node_id: 'n1', version, content_json: content });
function setup(save, initial) {
  const memory = new Map(initial);
  const storage = { getItem: k => memory.get(k) ?? null, setItem: (k,v) => memory.set(k,v), removeItem: k => memory.delete(k) };
  const store = new NodeDraftStore({ save, load: async () => node(9), storage, delay: 5 });
  store.ensure(node());
  return { store, memory, storage };
}

test('debounce merges edits made by multiple panels', async () => {
  const calls = [];
  const { store } = setup(async (id, content, version) => { calls.push({ id, content, version }); return node(version + 1, content); });
  store.edit('n1', d => { d.name = 'new'; });
  store.edit('n1', d => { d.section_order = ['skills']; });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].content, { name: 'new', section_order: ['skills'] });
  assert.equal(store.get('n1').status, 'saved');
});

test('edits during in-flight save are serialized against returned version', async () => {
  let release;
  const calls = [];
  const { store } = setup(async (id, content, version) => {
    calls.push({ content, version });
    if (calls.length === 1) await new Promise(r => { release = r; });
    return node(version + 1, content);
  });
  store.edit('n1', d => { d.name = 'first'; });
  const flushing = store.flush('n1');
  store.edit('n1', d => { d.summary = 'second panel'; });
  release();
  assert.equal(await flushing, true);
  assert.equal(calls.length, 2);
  assert.equal(calls[1].version, 1);
  assert.deepEqual(calls[1].content, { name: 'first', summary: 'second panel', version: 1 });
});

test('refresh restores the local draft and its original version', async () => {
  const { store, storage } = setup(async () => node());
  store.setComposing('n1', true);
  store.edit('n1', d => { d.name = 'unsaved'; });
  const calls = [];
  const restored = new NodeDraftStore({ storage, delay: 5, load: async () => node(), save: async (id, content, version) => { calls.push(version); return node(version+1, content); } });
  restored.ensure(node());
  assert.equal(restored.get('n1').content.name, 'unsaved');
  assert.equal(await restored.flush('n1'), true);
  assert.deepEqual(calls, [0]);
});

test('conflict retains draft and blocks automatic retries until explicit reload', async () => {
  let calls = 0;
  const { store, memory } = setup(async () => { calls++; throw new Error('HTTP 409: Conflict'); });
  store.edit('n1', d => { d.name = 'mine'; });
  assert.equal(await store.flush('n1'), false);
  assert.equal(store.get('n1').status, 'conflict');
  store.edit('n1', d => { d.name = 'still mine'; });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(await store.flush('n1'), false);
  assert.equal(calls, 1);
  assert.equal(memory.size, 1);
  await store.reload('n1');
  assert.equal(store.get('n1').content.name, 'original');
  assert.equal(store.get('n1').version, 9);
  assert.equal(memory.size, 0);
});

test('Chinese composition persists immediately but delays network save', async () => {
  let calls = 0;
  const { store, memory } = setup(async (id, content, version) => { calls++; return node(version+1, content); });
  store.setComposing('n1', true);
  store.edit('n1', d => { d.name = '中文'; });
  await new Promise(r => setTimeout(r, 20));
  assert.equal(calls, 0);
  assert.equal(memory.size, 1);
  store.setComposing('n1', false);
  assert.equal(await store.flush('n1'), true);
  assert.equal(calls, 1);
});

test('restored stale draft is not silently rebased on new server content', async () => {
  const { store, storage } = setup(async () => node());
  store.setComposing('n1', true);
  store.edit('n1', d => { d.name = 'old unsaved'; });
  let calls = 0;
  const restored = new NodeDraftStore({ storage, load: async () => node(), save: async () => { calls++; return node(); } });
  restored.ensure(node(2));
  assert.equal(restored.get('n1').status, 'conflict');
  assert.equal(await restored.flush('n1'), false);
  assert.equal(calls, 0);
  assert.equal(restored.get('n1').content.name, 'old unsaved');
});

test('network failure can retry without discarding the original version', async () => {
  let calls = 0;
  const { store } = setup(async (id, content, version) => {
    if (++calls === 1) throw new Error('offline');
    assert.equal(version, 0);
    return node(1, content);
  });
  store.edit('n1', d => { d.name = 'saved after retry'; });
  assert.equal(await store.flush('n1'), false);
  assert.equal(store.get('n1').status, 'error');
  assert.equal(await store.flush('n1'), true);
  assert.equal(store.get('n1').content.name, 'saved after retry');
});

test('switching nodes flushes each node independently', async () => {
  const calls = [];
  const { store } = setup(async (id, content, version) => { calls.push(id); return { ...node(version+1, content), node_id: id }; });
  store.ensure({ ...node(), node_id: 'n2' });
  store.edit('n1', d => { d.name = 'first'; });
  store.edit('n2', d => { d.name = 'second'; });
  await Promise.all([store.flush('n1'), store.flush('n2')]);
  assert.deepEqual(calls, ['n1', 'n2']);
  assert.equal(store.get('n1').content.name, 'first');
  assert.equal(store.get('n2').content.name, 'second');
});

test('failed reload keeps conflict draft intact', async () => {
  const store = new NodeDraftStore({
    save: async () => { throw new Error('HTTP 409'); },
    load: async () => { throw new Error('offline'); },
  });
  store.ensure(node());
  store.edit('n1', d => { d.name = 'keep me'; });
  await store.flush('n1');
  await store.reload('n1');
  assert.equal(store.get('n1').content.name, 'keep me');
  assert.equal(store.get('n1').status, 'conflict');
});

test('newly loaded full content hydrates an empty node with the same version', () => {
  const { store } = setup(async () => node());
  store.ensure({node_id: 'n2', version: 0});
  store.receive({node_id: 'n2', version: 0, content_json: {name: 'loaded'}});
  assert.equal(store.get('n2').content.name, 'loaded');
});

test('page exit flushes drafts for all nodes including an unfinished composition', async () => {
  const calls = [];
  const { store, memory } = setup(async (id, content, version) => { calls.push(id); return { ...node(version+1, content), node_id: id }; });
  store.ensure({ ...node(), node_id: 'n2' });
  store.setComposing('n1', true);
  store.edit('n1', d => { d.name = '输入中'; });
  store.edit('n2', d => { d.name = 'second'; });
  assert.equal(memory.size, 2);
  await store.flushAll();
  assert.deepEqual(calls.sort(), ['n1', 'n2']);
  assert.equal(memory.size, 0);
});

test('refresh acknowledges an accepted save whose response was lost during unload', async () => {
  const original = setup(async () => node());
  original.store.setComposing('n1', true);
  original.store.edit('n1', d => {
    d.name = 'accepted before unload';
    d.personal_info = { contact: { name: '张三', email: 'test@example.com' } };
    d.version = 0;
  });
  let calls = 0;
  const restored = new NodeDraftStore({ storage: original.storage, load: async () => node(), save: async () => { calls++; return node(); } });
  // Server field order differs; only the root metadata version may be ignored.
  restored.ensure(node(1, { version: 1, personal_info: { contact: { email: 'test@example.com', name: '张三' } }, name: 'accepted before unload' }));
  assert.equal(restored.get('n1').status, 'saved');
  assert.equal(restored.get('n1').version, 1);
  assert.equal(original.memory.size, 0);
  assert.equal(await restored.flush('n1'), true);
  assert.equal(calls, 0);
});

test('late full GET acknowledges identical pending draft without saving it twice', async () => {
  const original = setup(async () => node());
  original.store.setComposing('n1', true);
  original.store.edit('n1', d => { d.name = 'already on server'; });
  let calls = 0;
  const restored = new NodeDraftStore({ storage: original.storage, load: async () => node(), save: async () => { calls++; return node(); } });
  restored.ensure({ node_id: 'n1', version: 1 });
  assert.equal(restored.get('n1').status, 'conflict');
  restored.receive(node(1, { name: 'already on server', version: 1 }));
  assert.equal(restored.get('n1').status, 'saved');
  assert.equal(restored.get('n1').version, 1);
  assert.equal(original.memory.size, 0);
  assert.equal(await restored.flush('n1'), true);
  assert.equal(calls, 0);
});

test('acknowledgement never ignores nested version changes or array ordering', () => {
  for (const server of [
    { name: 'mine', project: { version: 2 }, skills: ['A', 'B'] },
    { name: 'mine', project: { version: 1 }, skills: ['B', 'A'] },
  ]) {
    const { store, memory } = setup(async () => node());
    store.setComposing('n1', true);
    store.edit('n1', d => { d.name = 'mine'; d.project = { version: 1 }; d.skills = ['A', 'B']; });
    store.receive(node(1, server));
    assert.equal(store.get('n1').status, 'conflict');
    assert.equal(store.get('n1').version, 0);
    assert.deepEqual(store.get('n1').content.project, { version: 1 });
    assert.equal(memory.size, 1);
  }
});
