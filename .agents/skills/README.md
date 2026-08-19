# Maintained project skills

`.agents/skills` is the authoritative project-skill directory. The repository
maintains `frontend-excellence-goal` and `reader-web-audit` here alongside the
smaller UI skills already present.

Validate the stable metadata contract with:

```bash
node .agents/skills/validate-project-skills.mjs
```

The validator is structural and offline. It does not read secrets, access the
network, start the product, deploy, or authorize any external action. Local
evaluation workspaces matching `.agents/skills/*-workspace/` stay ignored.

`.claude/skills` contains compatibility entrypoints only. Do not duplicate a
skill implementation there; update the canonical `.agents/skills` package.
