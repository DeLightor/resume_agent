export interface ContentChange { id: string; path: (string | number)[]; before: unknown; after: unknown }
const unsafe = new Set(['__proto__', 'constructor', 'prototype']);
export function contentDiff(before: Record<string, unknown>, after: Record<string, unknown>): ContentChange[] {
  const changes: ContentChange[] = [];
  function visit(a: unknown, b: unknown, path: (string | number)[]) {
    if (JSON.stringify(a) === JSON.stringify(b)) return;
    if (Array.isArray(a) && Array.isArray(b)) {
      for (let i = 0; i < Math.max(a.length, b.length); i++) visit(a[i], b[i], [...path, i]);
    } else if (a && b && typeof a === 'object' && typeof b === 'object' && !Array.isArray(a) && !Array.isArray(b)) {
      const aa = a as Record<string, unknown>, bb = b as Record<string, unknown>;
      for (const key of new Set([...Object.keys(aa), ...Object.keys(bb)])) {
        if (!unsafe.has(key) && !(path.length === 0 && key === 'version')) visit(aa[key], bb[key], [...path, key]);
      }
    } else changes.push({id: JSON.stringify(path), path, before: a, after: b});
  }
  visit(before, after, []);
  return changes;
}
export function applyChoices(base: Record<string, unknown>, changes: ContentChange[], accepted: Set<string>): Record<string, unknown> {
  const result = structuredClone(base);
  const additions: { parent: unknown[]; index: number; value: unknown }[] = [];
  // Reverse traversal makes removals at array indexes safe.
  for (const change of [...changes].reverse()) {
    if (!accepted.has(change.id) || change.path.some(p => unsafe.has(String(p)))) continue;
    let parent: any = result;
    for (const key of change.path.slice(0, -1)) parent = parent[key];
    const key = change.path[change.path.length - 1];
    if (change.after === undefined) {
      if (Array.isArray(parent)) parent.splice(Number(key), 1);
      else delete parent[key];
    } else if (Array.isArray(parent) && change.before === undefined) {
      additions.push({parent, index: Number(key), value: structuredClone(change.after)});
    } else parent[key] = structuredClone(change.after);
  }
  for (const addition of additions.sort((a, b) => a.index - b.index)) addition.parent.push(addition.value);
  return result;
}
