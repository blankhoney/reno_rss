# Claude compatibility entrypoints

The authoritative project skills live under `.agents/skills`. This directory
contains thin compatibility entrypoints for runtimes that discover project
skills under `.claude/skills`.

Validate the authoritative packages with:

```bash
node .agents/skills/validate-project-skills.mjs
```

Do not copy supporting contracts into this directory. Compatibility entrypoints
must load the matching canonical `SKILL.md` and follow it as the source of truth.
