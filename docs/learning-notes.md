# Learning notes

## 2026-08-20 — Final release candidate

- The original `my_rss` checkout remains an immutable evidence source. Release
  work is migrated into a clean branch rooted in the current remote `main`.
- Project skills are authoritative under `.agents/skills`. `.claude/skills`
  contains compatibility entrypoints only, and CI validates the authoritative
  packages directly.
- Release evidence is valid only when it binds the repository, workflow run,
  run attempt, full candidate SHA, artifact digest, and freshness boundary.
- Staging and production remain fail-closed until the shared-VPS lock and
  cross-site edge/probe contract are installed and tested.
