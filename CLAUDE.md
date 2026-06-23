# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Reno RSS / AI Reader — a self-hosted RSS research workspace. **Miniflux stays the source of truth for feeds/entries/read/star state**; everything AI Reader adds (LLM scores, Chinese summaries, read-later, project queue, feed visibility) is *derived/local* state in a separate Postgres database. Two custom apps sit on top of Miniflux: a Next.js UI and a Python scoring service.

Deeper design docs: `TECHNICAL.md` (architecture + security boundaries), `SPEC-CICD.md` (delivery spec), `docs/runbooks/` (ops), `docs/superpowers/{plans,specs}/` (original design/plan docs). Chinese mirrors exist as `*.zh-CN.md`.

## ⚠️ This is a teaching project — read before acting

`.cursor/rules/learning-mode.mdc` is `alwaysApply: true`. The user is doing VPS/Docker/auth-gateway/CI-CD for the **first time** and wants to *understand*, not just get working commands. This is a real constraint on how you work here, not boilerplate:

- Before a command or config change, explain in 1–3 sentences: what it does, why, and what breaks if skipped.
- Don't silently chain multiple causally-linked steps as "I did it for you" — surface each step and its success/failure signal.
- Flag every step touching secrets, exposed ports, the database, or production with an explicit ⚠️.
- **After any task that changes project behavior/architecture/process/deploy/debugging knowledge, update `docs/learning-notes.md` in the same reply** (format defined in the cursor rule). Pure read-only answers don't need a notes update.

`AGENTS.md` adds: prefer the simplest sufficient change (no speculative abstractions), make precise edits (don't reformat/refactor unrelated code), and define how each change is verified before claiming done.

## Architecture: the non-obvious parts

Six runtime services (Docker Compose): `caddy` (public TLS edge) → `authelia` (forward-auth) → `reader-web` (Next.js) + `miniflux`, with `scorer-worker` (Python) and `postgres` behind them. Caddy/Authelia are *the* access-control boundary; reader-web assumes the edge already authenticated business routes.

**Cross-service data contract (this trips people up):** both apps share one Postgres "scoring" database but own different tables.
- `scorer-worker` **writes** scores → table `item_scores` (plus `items_snapshot`, etc.). reader-web **reads** `item_scores` (`apps/reader-web/src/lib/scoring/repository.ts`) but never writes it.
- `reader-web` owns `reader_entry_states`, `entry_project_queue`, `reader_feed_preferences`.
- `scoring_settings` is declared in **both** DDL files — keep the two definitions in sync if you change it.
- Schema application is asymmetric: `scorer-worker` auto-applies its full DDL (`apps/scorer-worker/sql/001_init_scoring.sql`) on startup via `init_schema` (`src/main.py:281`). **reader-web's `src/lib/scoring/schema.sql` is NOT applied at runtime** — `getPool()` only opens a pool. Those tables must be created separately, so a fresh DB needs that SQL run manually.

**Scoring is event-driven — there is no polling loop.** `scorer-worker` is a stdlib `http.server.ThreadingHTTPServer` (no web framework) exposing `GET /healthz`, `POST /internal/score-entry`, `POST /webhooks/miniflux`. reader-web calls it over HTTP via `src/lib/scoring/service-client.ts`. POSTs require Basic Auth and **fail closed** if `SCORER_WEBHOOK_USERNAME/PASSWORD` are unset (every POST → 401). LLM (MiniMax) failures fall back to a length-based baseline row marked as failed/`error`, which is then hidden from score ranking.

**reader-web data flow:** App Router SSR pages (`src/app/page.tsx` reads `module`/`sort`/`lang`/`article` query params) → `src/lib/articles/server.ts` orchestrates a Miniflux fetch + enrichment from the scoring DB → filter/sort by module. `src/lib/scoring/db.ts:getPool()` is the single Postgres pool owner; `src/lib/miniflux/client.ts` is the only Miniflux caller (Node runtime only). Agent Q&A (`/api/agent/article-chat`) streams MiniMax over SSE.

## Invariants a refactor must preserve

- **HTML sanitization**: all article HTML passes `sanitizeArticleHtml()` (`src/lib/articles/service.ts`) before render — RSS/fetched content is untrusted.
- **`<think>` stripping + Markdown-only agent output**: agent SSE is cleaned by `src/lib/agent/stream.ts` (strip `<think>…</think>`); answers render through `AgentMarkdown` (no raw HTML) and the system prompt enforces fixed Chinese sections (结论/依据/引用/不确定点/行动建议). Agent input is length-capped server-side.
- **module → candidate → project flow**: an article must be starred (Miniflux) before `POST /api/articles/[id]/project` enqueues it into `entry_project_queue`.
- **markRead dual-write**: updates both Miniflux status *and* local `reader_entry_states.last_read_at`.
- **content quality / feed demotion**: `src/lib/articles/contentQuality.ts` classifies full vs partial (RSS fragment / blocked page) and decides whether a fetched body replaces the current one; `src/lib/feeds/quality.ts` computes a 0–100 feed quality score that demotes weak feeds. Hidden feeds are filtered out of most modules but preserved for starred/project/read-later.
- **public demo boundary (staging)**: only `GET /` (empty query), `POST /api/demo-login`, `/_next/static/*`, `/favicon.ico` are public; all business routes stay behind Authelia. `demo-login` reads server-side creds and rejects client-supplied username/password/target. Don't widen this surface.

## Commands

reader-web (`apps/reader-web/`, Node 22):
```bash
npm ci
npm test                 # node --test --import tsx 'src/**/*.test.ts'
npm run build            # next build (also the CI gate)
npm run dev              # local dev server
node --test --import tsx src/lib/scoring/repository.test.ts   # single test file
```
Tests are Node's built-in runner (no Jest/Vitest), `*.test.ts` co-located with source, using `node:assert/strict`. Many test SQL builders / pure transforms rather than hitting a real DB.

scorer-worker (`apps/scorer-worker/`, Python 3.12):
```bash
python -m pip install -e ".[dev]"
python -m pytest tests -q
python -m pytest tests/test_scoring.py::test_name -q   # single test
ruff check src/          # line-length 100
```

Compose config validation (must pass in CI; always include `--profile worker`, else scorer-worker is omitted):
```bash
cp .env.example .env
docker compose --profile worker --env-file .env \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.staging.yml config
```
Overlays: `base` = shared services; `prod`/`staging` = network aliases + env differences; `edge` = the single shared Caddy ingress. Any tracked edit should also pass `git diff --check`.

## CI/CD

`.github/workflows/ci.yml` runs on PRs and `main` pushes: ruff + pytest (scorer), `npm test` + `npm run build` (reader), compose validation across all overlays, Trivy fs scan (fails on CRITICAL/HIGH). Then it builds/pushes GHCR images tagged `sha-<short_sha>` and **auto-deploys staging** — but only for same-repo PRs and `main` pushes; **fork PRs skip image build/deploy** (no secrets). Production (`deploy-prod.yml`) is manual via the `production` environment; `rollback.yml` redeploys an older tag. Image tags must match the deployed revision. Remote deploy (`.github/scripts/remote-deploy.sh`) refuses to run if the VPS tracked worktree is dirty — diagnose the dirty file, don't auto-reset.

## Secrets & VPS

Never commit real `.env`, Authelia user DBs, API keys, or SSH keys; `.env.example` stays placeholder-only and the tracked `infra/authelia/users_database.yml` is a placeholder. For VPS/Caddy/DNS/Docker-daemon facts, prefer read-only diagnostics (`docs/runbooks/vps-agent-diagnostics.md`) over forcing changes, and never ask for or paste secret values — treat any leaked secret as compromised and recommend rotation. Staging demo credentials are a public experience password, not a production secret.
