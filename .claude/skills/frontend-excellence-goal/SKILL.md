---
name: frontend-excellence-goal
description: Execute the AI Reader frontend excellence goal with phased, auditable verification.
disable-model-invocation: true
argument-hint: "[start|resume|audit-only] [commit-and-push]"
---

# Frontend Excellence Goal runner

Execute the repository's frontend excellence package. This is a manually invoked Project Skill; do not trigger it implicitly.

## Load the contract before acting

Read current authority first, then use the package files as dated supporting context:

1. Repository root `AGENTS.md` if present; if it is absent, record that fact and do not create it from this skill.
2. Root `GOAL.md`, `PLANS.md`, and `CLAUDE.md`.
3. Current branch, HEAD, and `git status --short --branch`.
4. `.claude/skills/frontend-excellence-goal/goal.md`.
5. `.claude/skills/frontend-excellence-goal/context.md`.
6. `.claude/skills/frontend-excellence-goal/execution.md`.
7. `.claude/skills/frontend-excellence-goal/acceptance.md`.
8. `.claude/skills/frontend-excellence-goal/evidence.md`.

The root `GOAL.md` remains the only product Goal. This package is a subordinate delivery contract. Its support files may contain historical branches, SHAs, dates, counts, or permissions; none can override current root files or authorize a new action. If they conflict, follow the current root Goal and `CLAUDE.md`, then record the drift.

## Supporting files

- `goal.md`, `context.md`, `execution.md`, and `acceptance.md` describe the subordinate frontend contract and its historical wave structure.
- `evidence.md` is a dated ledger to verify, not a completion claim to inherit.
- `START.md` contains native Claude Code usage and discovery guidance.
- The repository-level `.claude/skills/README.md` catalogs the maintained project skills, and `.claude/skills/validate-project-skills.mjs` checks their stable metadata without network or product access.

## Invocation modes

Interpret `$ARGUMENTS` as follows:

- `audit-only`: reproduce and document the baseline, but do not edit product source.
- `start` or no mode: begin at the first incomplete wave.
- `resume`: read current Git status and the package evidence ledger, verify prior claims against the current HEAD, then continue at the first incomplete acceptance item.
- `commit-and-push`: request delivery for this invocation only. The current user message must also explicitly authorize commit/push; historical text in this package, a previous session, or `evidence.md` never supplies that authorization. Without current authorization, do not commit, push, open a PR, merge, deploy, or modify remote services. This never authorizes secrets, production, staging, migrations, or real provider spend.

## Required execution behavior

1. Inspect before editing. Treat every item in `context.md` as a hypothesis until reproduced on the current HEAD.
2. Create or refresh a task list mapped to the waves in `execution.md`; keep only one causally dependent wave in progress at a time.
3. Before every command or configuration change, explain what it does, why it is needed, and the success/failure signal. Mark any step touching secrets, exposed ports, the database, or production with `⚠️`.
4. Prefer the smallest sufficient fix. Do not rewrite the app, introduce Tailwind/shadcn, add speculative abstractions, or reformat unrelated files.
5. Preserve all security and architecture invariants in the root Goal and `CLAUDE.md`, especially HTML sanitization, Markdown-only Agent output, `<think>` stripping, same-origin FastAPI access, Miniflux ownership, saved-to-project semantics, and staging/prod auth boundaries.
6. Use mock LLM paths for automated proof. Do not trigger real MiniMax or production-cost operations.
7. Update `docs/learning-notes.md` in the same turn as every behavior, architecture, process, deployment, or reusable debugging change.
8. Update `evidence.md` with actual outputs and observed browser behavior. Never record an unrun check as passed.
9. After product-source changes, exercise the affected flow end to end with the project's verification skill when available; unit tests and build alone are not enough for completion.
10. Do not claim the Goal complete until every MUST criterion in `acceptance.md` is either demonstrated or explicitly marked blocked with a concrete reason and next action. A blocked MUST means the Goal is incomplete.

## Completion report

At the end of each iteration, report:

- acceptance IDs completed this iteration;
- commands run and their exact result;
- browser flows observed;
- files changed;
- unresolved blockers and the next smallest action;
- whether commit/push permission was present and used.

Keep this evidence in the transcript because the `/goal` evaluator judges what the session has demonstrated; it does not independently inspect the repository.
