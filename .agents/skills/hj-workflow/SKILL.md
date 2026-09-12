---
name: hj-workflow
description: Use when HJ asks to start, plan, execute, verify, integrate, or refine development work using his standard workflow across requirements, specs, implementation, QA, review, and release.
---

# HJ Workflow

Use this skill as HJ's project-independent development workflow coordinator. Apply it to the current repository by reading that project's own source of truth, commands, and agent instructions.

This skill does not replace specialist skills. It decides the phase, risk level, required gates, and which specialist skill or gstack review/QA skill to invoke.

## Core Principle

Run a fixed main chain, then choose tools inside each phase by explicit conditions.

```text
需求进入
-> 需求澄清
-> 风险分级
-> 工作区隔离
-> 规格/计划
-> 实现前评审
-> TDD/实现
-> 自动验证
-> 交付前 review
-> QA
-> HJ 人工验收
-> archive/commit/merge/push/cleanup
-> retro/沉淀
```

Do not write vague alternatives such as "A or B" without deciding which condition applies. State the classification briefly, then execute the matching rule.

OpenSpec remains the durable specification source when a spec is needed. gstack, brainstorming, review, QA, and retro outputs are review evidence or improvement inputs; fold accepted decisions back into the spec, plan, project docs, or skill rather than creating a second source of truth.

## Project Context

Before scoping implementation, read the current project's source of truth. Prefer, when present:

- Product requirements or PRDs.
- Architecture, API, database, or implementation plans.
- Page flow, UX, or design specs.
- Agent/project instructions such as `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `README.md`, or equivalents.

Keep the workflow project-independent. Do not bake one project's tech stack, scope, commands, or release policy into this skill; use the current repository's own instructions for those details.

## Risk Tiers

Classify the task before choosing gates. If unsure, choose the higher tier.

### Lightweight

Use for copy changes, obvious typo fixes, local styling adjustments, small config/docs edits, and isolated non-behavioral changes.

- May skip OpenSpec and gstack plan review.
- Must explain the skip reason.
- Must still run the smallest relevant verification.

### Standard

Use for normal user-facing features, page flows, API behavior, non-critical bugfixes, ordinary refactors, and changes with contained blast radius.

- Use branch isolation.
- Use a written plan or OpenSpec when behavior changes.
- Use TDD where production behavior changes.
- Run automatic verification.
- Run delivery review and QA when user-facing.

### High Risk

Use for database schema, migrations, auth, permissions, billing/payment, orders, audit logs, deletion, irreversible operations, core state machines, cross-client contracts, security, production data, or changes with unclear rollback.

- OpenSpec change is required.
- Implementation plan/review is required before coding.
- TDD is required for behavior changes.
- gstack plan review is required for the relevant risk area.
- Delivery review, QA evidence, and HJ smoke approval are required before archive or merge.
- Do not auto-fix risky QA findings without reporting the risk first.

## Engineering Constraints

- Read the project source of truth before implementing features.
- Local project documentation takes precedence over general coding preferences.
- Do not perform drive-by refactors.
- Preserve existing API, database, event, and client contracts unless the approved specification explicitly changes them.
- Follow established project conventions for mock data, configuration, and file organization.
- Do not invent new locations, patterns, or structures when an existing convention already exists.
- Do not add dependencies, external services, infrastructure, code generators, or build tools without approval.
- Do not change the repository structure, architecture, or technology stack without approval.
- Prefer extending existing modules and components over creating parallel implementations.

## Phase Rules

### 1. Requirement Clarification

Default: determine whether HJ wants discussion, planning, or execution.

- If HJ says "先不改代码", "先分析", "先讨论", "先看一下", or equivalent, stop before branch creation or file edits.
- If the request is product-definition heavy, scope is unclear, or the target user/value is fuzzy, use `gstack-office-hours` when available.
- If the requirement is mostly clear and only boundaries/tradeoffs need confirmation, use `brainstorming`.
- If the requested output is a PRD or major PRD revision, use `openspec` and the project planning workflow.
- If HJ provides an approved spec or implementation plan, do not re-open broad discovery; do a short understanding check and proceed.

Ask one focused question at a time only when a reasonable assumption would be risky.

### 2. Workspace Isolation

Before implementation, isolate the work unless HJ explicitly says analysis-only.

1. Check current git status and preserve user changes.
2. Prefer switching to `develop` and pulling `origin develop` when the repository uses that flow.
3. Create a feature branch named `codex/<topic>` for implementation.
4. Use `using-git-worktrees` when the current workspace should remain untouched, multiple agents need isolated writes, or project policy prefers worktrees.

Do not make feature changes directly on `develop` unless HJ explicitly instructs that.

### 3. Specification And Planning

- Use `openspec` for user-visible features, behavior changes, planned bugfixes, and high-risk work.
- Create one OpenSpec change per coherent outcome; prefer small independent changes over mixed batches.
- Expected OpenSpec artifacts are `proposal.md`, `tasks.md`, and `design.md` when architecture, data, UX, or integration implications exist, plus spec deltas when required.
- Use `writing-plans` after an approved design when implementation needs multi-step sequencing.
- Lightweight tasks may skip OpenSpec only after stating why they are lightweight.

Accepted decisions from discussion, gstack plan review, or HJ feedback must be reflected in the spec or plan before implementation continues.

### 4. Pre-Implementation Review

Read the current spec/plan before coding. Check scope, acceptance criteria, data flow, test strategy, and rollout risk.

- Use `gstack-plan-ceo-review` when product value, scope cuts, prioritization, or non-MVP creep is uncertain.
- Use `gstack-plan-eng-review` when architecture, API contracts, database changes, state transitions, concurrency, migration, integration, or test matrix risk exists.
- Use `gstack-plan-design-review` when UX, UI flow, interaction quality, or visual design risk exists.
- Use `gstack-autoplan` only when multiple plan review lenses are clearly needed.
- Use `gstack-plan-eng-review` for cross-layer scope, API/data/client boundaries, and implementation-risk review.

If a plan review is skipped for a standard or high-risk task, state the concrete reason.

### 5. Implementation

Use `test-driven-development` before writing production code for features, bugfixes, refactors, and behavior changes.

Follow red-green-refactor:

- Write a focused failing test first.
- Run it and confirm the failure is for the intended missing behavior.
- Implement the smallest production change that passes.
- Run the focused test and relevant surrounding checks.
- Refactor only after green.

Invoke specialist skills by touched area:

- Backend/API/database/auth/data models/migrations: use `fastapi-expert` for FastAPI work; otherwise rely on the native model and the project's own documentation.
- Frontend/UI/UX/web/mobile/client experience: use `ui-ux-pro-max`.
- Failing tests, broken flows, unexpected output, or user-reported bugs: use `systematic-debugging`.
- Multiple independent implementation slices: use Codex's native parallel-agent support only when write scopes and dependencies are clear.

Keep edits aligned with the current repository's structure and conventions. Do not introduce unrelated refactors or new infrastructure without HJ approval.

### 6. Automatic Verification

Use `verification-before-completion` before claiming success, committing, archiving, merging, or pushing.

Run the smallest relevant verification set documented by the current project:

- Backend: relevant tests, linters, API/schema checks, and migration checks when applicable.
- Frontend: typecheck, lint, build, and focused UI tests when available.
- Database: migration upgrade/current checks against the intended local database.
- OpenSpec: project OpenSpec validation command.
- General hygiene: `git diff --check` or the local equivalent when available.

Report warnings separately from failures. Do not describe a task as passing if only part of verification ran.

### 7. Delivery Review

Use delivery review after automatic verification for standard/high-risk changes and before HJ smoke testing.

- Use `gstack-review` when available for diff-level regression, missing tests, hidden production risks, and ship-readiness concerns.
- Use `gstack-review` when the change is large, risky, or touches shared contracts.
- Interpret HJ or reviewer feedback directly in the current task, then run focused verification.

Classify review findings as must-fix, can-follow-up, or not-adopted-with-reason. Must-fix items stay in the same branch and return to implementation plus verification.

### 8. QA

QA is separate from unit/build verification. It checks whether the product flow works.

- Default to `gstack-qa-only` for report-only QA before HJ manual smoke testing.
- Use `gstack-qa` only when HJ authorizes "发现就修", or the issue is clearly within the approved current scope and not high-risk.
- Use browser/playwright skills for real browser evidence when the change affects web UI, mobile-web-like flows, screenshots, layout, navigation, forms, or user journeys.
- For high-risk data, permissions, production, deletion, migrations, or irreversible operations, report QA findings and proposed fixes before changing code.

QA findings that are fixed must be followed by focused regression verification.

### 9. HJ Manual Smoke Test

When the flow is user-facing, start the needed local services and give HJ exact manual test steps.

- Keep servers running while HJ tests when practical.
- Explain account, role, seed data, or login state assumptions.
- Give a short ordered path through the feature.
- Treat HJ's observed issues as first-class feedback.
- Make small fixes in the same branch when they fit the approved scope.

Do not archive, commit, merge, or push until HJ approves the manual flow or explicitly says to proceed without manual testing.

### 10. Archive, Commit, Merge, Push, Cleanup

Use the native git/worktree workflow when implementation is complete and HJ asks to integrate, merge, push, or clean up.

After implementation, verification, review, QA, and HJ approval:

1. Run OpenSpec verification when an OpenSpec change exists.
2. Archive the completed OpenSpec change.
3. Re-run required verification after archive if specs or generated artifacts changed.
4. Stage only intended files.
5. Commit with a clear message.
6. Switch to the integration branch, usually `develop`.
7. Pull the remote integration branch.
8. Merge the feature branch.
9. Run relevant verification again on the merged branch.
10. Push the integration branch.
11. Delete the merged task branch after successful push, unless HJ asks to keep it.

Never delete `develop`, `main`, unmerged branches, migrations, user-provided assets, or long-lived branches without explicit HJ approval. Never use force deletion unless HJ explicitly asks.

### 11. Retro And Learning

Use retro only when there is something reusable to preserve.

- Use `gstack-retro` when a task exposes a repeated failure mode, process gap, QA pattern, release risk, or useful preference.
- Use `gstack-learn` or update the appropriate project/skill documentation only for durable rules, not one-off trivia.
- Keep project-specific lessons in project docs or agent instructions.
- Keep cross-project workflow improvements in this skill or another personal skill.

## Skip Rules

Skipping a gate is allowed only when the task classification permits it.

When skipping, state:

- The skipped gate.
- The risk tier.
- The reason it is safe to skip.
- What verification still covers the risk.

Do not skip gates because the task "looks easy" if it affects core behavior, data, permissions, release, or user-facing flows.

## Communication Defaults

- Prefer Chinese responses unless HJ asks otherwise.
- Keep HJ updated before edits, long verification, service startup, QA, archive, merge, and push.
- State current phase, risk tier, and next action when the work is substantial.
- Be explicit about what changed, what was verified, what remains unverified, and current branch state.
- When a command fails, state the failure and next corrective action instead of claiming progress.

## Stop Conditions

Stop and ask HJ before:

- Expanding beyond approved scope.
- Adding paid services or new infrastructure.
- Changing tech stack or repository structure.
- Changing product/API semantics instead of implementing them.
- Deleting files, branches, migrations, user-provided assets, or durable project artifacts.
- Performing irreversible data operations.
- Merging when verification, review, QA, or HJ smoke approval has failed or is incomplete.
