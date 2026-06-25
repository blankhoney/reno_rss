# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Reno RSS / AI Reader — a self-hosted RSS research workspace. **Miniflux stays the source of truth for feeds/entries/read/star state**; everything AI Reader adds (LLM scores, Chinese summaries, recommendations, content fetch state, project queues, feed visibility) is *derived/local* state in a separate Postgres database. Three custom apps sit on top of Miniflux: a FastAPI API, a Python queue worker, and a Next.js UI.

Deeper design docs: `TECHNICAL.md` (architecture + security boundaries), `SPEC-CICD.md` (delivery spec), `docs/runbooks/` (ops), `docs/superpowers/{plans,specs}/` (original design/plan docs). Chinese mirrors exist as `*.zh-CN.md`.

## ⚠️ This is a teaching project — read before acting

`.cursor/rules/learning-mode.mdc` is `alwaysApply: true`. The user is doing VPS/Docker/auth-gateway/CI-CD for the **first time** and wants to *understand*, not just get working commands. This is a real constraint on how you work here, not boilerplate:

- Before a command or config change, explain in 1–3 sentences: what it does, why, and what breaks if skipped.
- Don't silently chain multiple causally-linked steps as "I did it for you" — surface each step and its success/failure signal.
- Flag every step touching secrets, exposed ports, the database, or production with an explicit ⚠️.
- **After any task that changes project behavior/architecture/process/deploy/debugging knowledge, update `docs/learning-notes.md` in the same reply** (format defined in the cursor rule). Pure read-only answers don't need a notes update.

`AGENTS.md` adds: prefer the simplest sufficient change (no speculative abstractions), make precise edits (don't reformat/refactor unrelated code), and define how each change is verified before claiming done.

## Architecture: the non-obvious parts

Runtime services (Docker Compose): `caddy` (public TLS edge), `authelia` (forward-auth), `reader-web` (Next.js), `ai-reader-api` (FastAPI), `ai-reader-worker` (Python queue worker), `miniflux`, and `postgres`. Caddy routes `/api/*` directly to FastAPI; API endpoints enforce `require_user` / `require_admin` themselves. Web pages are served by `reader-web`, with staging exposing the root app shell and static assets publicly while other page routes remain behind Authelia.

**Cross-service data contract (this trips people up):** `apps/api` owns the HTTP API and database schema via Alembic; `apps/worker` owns background jobs for Miniflux sync, content fetch, LLM scoring, and Top10 recommendation generation; `apps/reader-web` does not call Miniflux or Postgres directly. The browser app calls same-origin FastAPI `/api/*` through `apps/reader-web/src/lib/api/*` adapters.

**Scoring is queue-driven — there is no old HTTP scorer service.** Admin scoring creates batches through FastAPI, enqueues jobs in Postgres, and `ai-reader-worker` processes them. LLM provider defaults to `mock` in automated staging proof; MiniMax is used only when deliberately configured.

**reader-web data flow:** App Router pages parse URL state, then client components load data through FastAPI adapters: `/api/auth/*`, `/api/articles`, `/api/recommendations/latest`, `/api/articles/{id}/ask`, `/api/admin/*`, and `/api/jobs/{id}`. Article HTML is still sanitized in `src/lib/articles/service.ts` before render.

## Invariants a refactor must preserve

- **HTML sanitization**: all article HTML passes `sanitizeArticleHtml()` (`src/lib/articles/service.ts`) before render — RSS/fetched content is untrusted.
- **`<think>` stripping + Markdown-only agent output**: article ask SSE is cleaned by `src/lib/agent/stream.ts` (strip `<think>…</think>`); answers render through `AgentMarkdown` (no raw HTML). Agent input is assembled server-side by FastAPI and length-capped there.
- **saved → project flow**: project/candidate state changes go through FastAPI article state APIs; reader-web must not recreate direct Miniflux or database write paths.
- **content quality / feed demotion**: `src/lib/articles/contentQuality.ts` classifies full vs partial (RSS fragment / blocked page) and the API/worker owns fetched-content replacement. Feed quality scores arrive as API fields and are used only for client sorting/demotion.
- **staging public boundary**: Caddy routes `/api/*` to FastAPI and only exposes the root app shell/static assets publicly; do not reintroduce public Next API route handlers.

## Commands

reader-web (`apps/reader-web/`, Node 22):
```bash
npm ci
npm test                 # node --test --import tsx 'src/**/*.test.ts'
npm run build            # next build (also the CI gate)
npm run dev              # local dev server
```
Tests are Node's built-in runner (no Jest/Vitest), `*.test.ts` co-located with source, using `node:assert/strict`. Many test SQL builders / pure transforms rather than hitting a real DB.

api (`apps/api/`, Python 3.12):
```bash
uv run --isolated --with-editable . --extra dev python -m pytest tests -q
uv run --isolated --with-editable . --extra dev ruff check .
uv run --isolated --with-editable . --extra dev alembic upgrade head
```

worker (`apps/worker/`, Python 3.12):
```bash
uv run --isolated --with-editable . --extra dev python -m pytest tests -q
uv run --isolated --with-editable . --extra dev ruff check .
```

Compose config validation (must pass in CI; include `--profile worker` for the current worker overlay):
```bash
cp .env.example .env
docker compose --profile worker --env-file .env \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.staging.yml config
```
Overlays: `base` = shared services; `prod`/`staging` = network aliases + env differences; `edge` = the single shared Caddy ingress. Any tracked edit should also pass `git diff --check`.

## CI/CD

`.github/workflows/ci.yml` runs on PRs and `main` pushes: API/worker ruff + pytest, reader-web `npm test` + `npm run build`, compose validation across all overlays, deploy-script checks, Trivy fs scan (fails on CRITICAL/HIGH). Then it builds/pushes GHCR images for `ai-reader-web`, `ai-reader-api`, and `ai-reader-worker` tagged `sha-<short_sha>` and **auto-deploys staging** — but only for same-repo PRs and `main` pushes; **fork PRs skip image build/deploy** (no secrets). Production (`deploy-prod.yml`) is manual via the `production` environment; `rollback.yml` redeploys an older tag. Image tags must match the deployed revision. Remote deploy (`.github/scripts/remote-deploy.sh`) refuses to run if the VPS tracked worktree is dirty — diagnose the dirty file, don't auto-reset.

## Secrets & VPS

Never commit real `.env`, Authelia user DBs, API keys, or SSH keys; `.env.example` stays placeholder-only and the tracked `infra/authelia/users_database.yml` is a placeholder. For VPS/Caddy/DNS/Docker-daemon facts, prefer read-only diagnostics (`docs/runbooks/vps-agent-diagnostics.md`) over forcing changes, and never ask for or paste secret values — treat any leaked secret as compromised and recommend rotation. Staging demo credentials are a public experience password, not a production secret.
