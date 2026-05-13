# AGENTS.md

This file is the general agent entrypoint for this repository. It applies to
the whole repo unless a more specific `AGENTS.md` is added in a subdirectory.

## Rule Sources

- Treat this file as the primary guidance for Codex and general coding agents.
- Treat `.cursor/rules/*.mdc` as Cursor-specific helper rules. Do not assume
  Codex or other agents automatically load them.
- Use `docs/runbooks/` for operational procedures and copyable VPS prompts.

## Development Rules

1. Think before coding.
   - Before changing files, state the understanding, assumptions, and unknowns
     when the task is ambiguous.
   - If multiple interpretations materially change the result, ask first.

2. Prefer the simplest sufficient change.
   - Implement only what the current task needs.
   - Do not add speculative features, abstractions, config, or future extension
     points.

3. Make precise edits.
   - Only change files directly related to the task.
   - Do not reformat, refactor, or optimize unrelated code.
   - Mention unrelated issues separately instead of editing them.

4. Execute toward verifiable success.
   - Define success criteria before implementation.
   - For bugs: reproduce or identify the failure, fix it, then verify.
   - For features: define acceptance criteria, implement, then test.
   - For multi-step work: use a short plan and state how each step is verified.

## Learning Notes

- Update `docs/learning-notes.md` whenever a task changes project behavior,
  process, architecture, deployment, or debugging knowledge.
- Pure read-only answers do not require a notes update if they add no durable
  project progress.

## VPS Work

- For VPS-only facts such as real `.env`, Docker daemon state, Caddy TLS, DNS,
  or live container logs, prefer a read-only diagnostic prompt before proposing
  changes.
- Do not ask the user or VPS agent to paste `.env` contents, passwords, tokens,
  cookies, or API keys.
- Use `docs/runbooks/vps-agent-diagnostics.md` as the standard prompt for AI
  Reader staging diagnostics.
- If a secret is pasted into chat or logs, treat it as leaked and recommend
  rotation before production use.
