# US-32 verification — 2026-09-09

Status: Implementation, automated verification, independent delivery review and browser QA complete. HJ manual smoke accepted on 2026-09-10; archive and commit authorized. Archived on 2026-09-10 for commit on `codex/edit-protection`.

## Automated evidence

- `UV_CACHE_DIR=/private/tmp/resume-uv-cache make test`: **432 passed**, frontend tsc passed. Log `/private/tmp/us32-verified.log`.
- `make lint`: Ruff and TypeScript passed.
- `make build`: production build passed; existing >500 kB bundle warning remains.
- `node --experimental-strip-types --test frontend/tests/contentDiff.test.ts frontend/tests/nodeDrafts.test.mjs`: **18 passed** (4 diff / 14 autosave).
- `openspec validate edit-protection --strict`: passed.
- `git diff --check`: passed.
- Existing Starlette/httpx and Swig deprecation warnings remain.

## Independent review

Confirmed fixed: create/delete parent race, stale upstream notifications after undo, soft-deleted Diff access, holes from selectively accepting appended array items, right-panel saves not syncing the shared draft, late responses switching the selected node, mutation with an unseen latest version, overlapping generation retaining old decisions.

Each behavior fix received focused regression verification. Final independent recheck reports no remaining blockers in these paths.

## Browser QA

Browser: Chromium via Playwright CLI. URL: `http://127.0.0.1:5173`. Backend: port 8000. Isolated data: `/private/tmp/us31-manual`, not the user's default database. Synthetic node: `US32编辑保护验收`.

Verified against actual local storage/API:

1. Edit personal information and preview rapidly, switch tabs, both fields persist.
2. Immediately reload after editing: content recovers, an already completed save does not become a false conflict.
3. History buttons and Cmd+Z / Cmd+Shift+Z restore actual content; input-native undo is excluded from the node handler.
4. Soft-delete and restore the synthetic branch: it returns with content intact.
5. Simulated second writer: stale editor receives conflict, retains local text, server content remains intact.
6. AI result does not write before approval; reject one field / accept another preserves the rejected content.
7. A second writer during AI review makes confirmation fail without overwriting or discarding the AI draft.
8. Right-panel generated result passes review, syncs center preview, and subsequent manual editing saves without a stale-version conflict.

AI/JD browser responses were deterministic Playwright route fixtures; real node read/write/history/trash APIs were used. Real provider output quality/availability was not retested. Backend generation tests cover no-write and concurrent-edit behavior. Browser fixture routes were removed before HJ handoff.

Screenshots retained locally under `.playwright-cli/us32/` (not staged). Existing favicon 404, React Router future warnings and React Flow edge fallback warnings were observed. Expected HTTP409s were produced deliberately by conflict scenarios; no new uncaught UI errors were observed.

## HJ smoke steps

1. Open `http://127.0.0.1:5173`, select `US32编辑保护验收` or another test node, enter 编辑器.
2. Edit name and self-summary, wait for 已保存, then refresh and reselect the node.
3. Open 编辑历史 / 撤销; test 撤销/重做 and Cmd/Ctrl+Z / Shift+Z outside text inputs.
4. Upload/analyze a JD and generate. Review old/new differences, reject/accept fields, then confirm; cancel should not modify the node.
5. Return to 版本树, delete a test branch, then 回收站 → 恢复; confirm contents return.
6. Optional: open two windows on one node. Save in one, edit in the other; confirm conflict and preserved draft rather than overwrite.

Do not archive/commit/merge/push until HJ approves this manual flow.

## Final acceptance fixes — 2026-09-10

History displays concrete Chinese field paths. Legacy history reconstructs differences from adjacent snapshots without rewriting stored content; the oldest retained snapshot may lack its predecessor. Removed the partial-result PDF export from the generation sidebar. Regression: 11 edit-protection tests passed; browser verified “修改 个人信息 / 联系方式 / 姓名”. HJ confirmed “现在好了 可以归档提交了”.

Final pre-commit verification: 434 backend tests passed (189.74s), TypeScript/Ruff/build passed, 18 frontend tests passed, all 2 formal OpenSpec specifications validated. Log: /private/tmp/us32-archive-tests.log. Existing dependency and bundle warnings only.
