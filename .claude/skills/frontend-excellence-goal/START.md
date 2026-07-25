# Start this Goal yourself

## What is official and what is project-defined

Claude Code's official feature is the session command `/goal`; it does **not** define a repository `goal.md` format. The official repository entry in this package is the Project Skill:

```text
.claude/skills/frontend-excellence-goal/SKILL.md
```

The neighboring Markdown files are project-defined support contracts that the Skill explicitly loads.

## Prerequisite

Use Claude Code v2.1.139 or newer, because `/goal` requires that version or later.

## Safe default start

From the repository root:

```bash
claude -n frontend-excellence
```

Then invoke the manually gated Skill:

```text
/frontend-excellence-goal start
```

After the Skill has loaded the package and summarized the baseline, set the session goal by pasting this condition:

```text
/goal Complete the manually invoked frontend-excellence-goal package on the current repository. Completion requires every MUST item FEX-01 through FEX-32 in acceptance.md to be demonstrated in evidence.md and summarized in this transcript; reader-web npm test and npm run build must pass; git diff --check must pass; required browser checks must cover service-worker session isolation and queued-to-terminal freshness, mobile layers at the listed breakpoints, keyboard and modal behavior, article return context, search race and partial failure, research recovery, annotation selection, light/dark and reduced motion; root GOAL.md and CLAUDE.md invariants must remain true; no unrun check may be claimed as passed; no secret, production action, real LLM spend, commit, push, PR, merge, or deploy is allowed without explicit user permission. If a required item is blocked, record the exact blocker and next action and keep the goal incomplete. Stop after 80 turns if still incomplete and provide a precise handoff.
```

The Skill must be invoked first because the `/goal` evaluator only sees evidence already placed in the session transcript; it does not independently open these files or run commands.

## Resume later

If the session closes while the goal is active:

```bash
claude --resume frontend-excellence
```

Then invoke:

```text
/frontend-excellence-goal resume
```

Check current goal status with:

```text
/goal
```

The active goal survives session resume, although timer/turn/token baselines reset. `/clear` clears it.

## Audit without implementation

To reproduce the baseline and fill the first evidence rows without editing product source:

```text
/frontend-excellence-goal audit-only
```

Do not add `/goal` unless you want the session to continue autonomously after the audit response.

## Explicitly authorizing Git delivery

The default Skill invocation does not commit or push. If you intentionally want the executing session to create a branch, make focused commits, and push them, invoke:

```text
/frontend-excellence-goal start commit-and-push
```

That argument is explicit authorization for Git delivery only. It does not authorize deployment, production changes, secret access, or real LLM spending.

## Stop or cancel

```text
/goal clear
```

You can also exit Claude Code. Resume the named session if you want to continue with its active goal and transcript evidence.

## Official references

- `/goal`: https://code.claude.com/docs/en/goal.md
- Project Skills: https://code.claude.com/docs/en/skills.md
- Sessions: https://code.claude.com/docs/en/sessions.md
