# Maintained project skills

These are the two project-local Claude Code skills maintained by this repository:

| Directory | Native command | Invocation model |
|---|---|---|
| `frontend-excellence-goal/` | `/frontend-excellence-goal` | Manual-only task runner |
| `reader-web-audit/` | `/reader-web-audit` | Manual-only, read-only-by-default audit |

Each skill has a `SKILL.md` entrypoint. Supporting contracts and evaluation files stay
inside the skill directory and are loaded only when the entrypoint references them.
The directory name supplies the native project command; an optional frontmatter
`name` is only a display label for these project skills.

Validate the stable local metadata contract with:

```bash
node .claude/skills/validate-project-skills.mjs
```

This validator is structural only. It does not emulate every Claude Code parser,
open a native session, read secrets, access `.env`, start the product, use a
provider, modify `GOAL.md`, deploy, or grant permission for any external action.
A fresh native Claude Code session and its slash-command picker are the direct
proof of runtime discovery. The API harness may have a separate static skill
registry and can report a project command as unknown without contradicting native
Claude Code discovery.

Paths matching `.claude/skills/*-workspace/` are local evaluation artifacts and
remain ignored. Do not copy skills into `.claude/commands`, `~/.claude/skills`, or
the unrelated `.agents/skills` tree as a workaround. Adding another maintained
project skill requires a deliberate manifest/catalog update and a dedicated
validation/evidence change.
