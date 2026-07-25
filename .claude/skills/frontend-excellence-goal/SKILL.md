---
description: Execute the AI Reader frontend excellence goal with phased, auditable verification.
disable-model-invocation: true
argument-hint: "[start|resume|audit-only] [commit-and-push]"
---

# Frontend Excellence Goal runner

Execute the repository's frontend excellence package. This is a manually invoked Project Skill; do not trigger it implicitly.

## Load the contract before acting

Read these files in order:

1. Repository root `GOAL.md`, `CLAUDE.md`, and `AGENTS.md`.
2. `.claude/skills/frontend-excellence-goal/goal.md`.
3. `.claude/skills/frontend-excellence-goal/context.md`.
4. `.claude/skills/frontend-excellence-goal/execution.md`.
5. `.claude/skills/frontend-excellence-goal/acceptance.md`.
6. `.claude/skills/frontend-excellence-goal/evidence.md`.

The root `GOAL.md` remains the only product Goal. This package is a subordinate delivery contract. If they conflict, stop and follow the root Goal and `CLAUDE.md`.

## Invocation modes

Interpret `$ARGUMENTS` as follows:

- `audit-only`: reproduce and document the baseline, but do not edit product source.
- `start` or no mode: begin at the first incomplete wave.
- `resume`: read `evidence.md` and Git status, verify prior claims, then continue at the first incomplete acceptance item.
- `commit-and-push`: explicit permission to commit and push focused progress. Without this exact argument, do not commit, push, open a PR, merge, deploy, or modify remote services. If permission is present and the current branch is the default branch, create a feature branch before the first commit.

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
