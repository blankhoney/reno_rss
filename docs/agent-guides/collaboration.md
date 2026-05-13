# Agent Collaboration Guide

This is optional reference material for agent sessions. Read it when the task
needs teaching-style explanations, learning-note maintenance, or VPS diagnosis.

## Learning Workflow

- Explain non-obvious commands or configuration changes before suggesting them.
- After commands, name the output that proves success or failure.
- For secret, database, networking, or production deployment work, call out the
  concrete risk before proposing an action.
- Keep durable project knowledge in `docs/learning-notes.md` when the task
  changes behavior, process, architecture, deployment, or debugging practice.

## Teaching-Style Answers

When the user asks for teaching or conceptual explanation, include only the
parts that help the current question:

1. What the component or command does.
2. Which details connect it to the rest of this repo.
3. Why this approach was chosen and what tradeoff it makes.
4. Where to inspect the relevant file or runbook.

## Learning Notes Refresh

Before answering questions about prior tasks, project progress, or recorded
concepts, read `docs/learning-notes.md` from disk so the answer is based on the
current file rather than stale chat context.

## VPS Diagnosis

For VPS-only state, use `docs/runbooks/vps-agent-diagnostics.md` as the
copyable, read-only diagnostic prompt. Do not request raw `.env` contents or
secrets.
