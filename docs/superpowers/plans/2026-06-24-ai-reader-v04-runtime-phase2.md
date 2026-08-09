# AI Reader v0.4 Runtime Activation — Phase 2 Plan

> SUPERSEDED by `2026-06-24-ai-reader-v04-completion-roadmap.md` on 2026-06-24 — historical reference only. Deployment commands and workflow examples in this file are archived; do not execute them directly.

> **For agentic workers:** Implement task-by-task with TDD. Steps use checkbox (`- [ ]`). Read `docs/spec/ARCHITECTURE.md` §4–§8, `docs/spec/DATA_MODEL.md`, `docs/spec/SCORING_RUBRIC.md`, `docs/spec/DEPLOYMENT.md` before coding. Reuse-not-rewrite: port from `apps/scorer-worker` and `apps/reader-web`.
>
> **Supersedes** the remaining-task list in `2026-06-24-ai-reader-v04-runtime-activation.md`. That doc's Task 13 is **done**; its locked MVP decisions still hold (manual scheduler, preserve warm-paper frontend, `WORKER_CONCURRENCY=1`, Task 20 gets its own plan). This file is the single source of truth for everything after Task 13.
>
> **Status:** DESIGN ONLY. To be reviewed by Codex before implementation.

---

## 1. Where we are

Task 13 (worker runtime loop + state machine + deploy liveness + migrate-on-deploy) is committed and green (28 worker tests). The engine claims jobs, dispatches by `job_type`, drives `queued→running→succeeded/failed`, retries with backoff, stops gracefully on SIGTERM/SIGINT, starts on staging, and has an LLM-free liveness smoke check.

This phase does two things, in order:
1. **Harden the engine** (Tasks 13.5–13.6) from the post-Task-13 review — *before* real long-running LLM jobs and any prod migration land on top of it.
2. **Wire the capabilities** (Tasks 18, 14, 17, 15, 16, 19) so 评分 / 抓取 / 推荐 / AI 阅读 actually run, then the frontend cutover (Task 20).

## 2. Execution order (unlock order; task numbers are stable references, not execution order)

1. **Task 13.5 — Worker queue hardening** (reclaim stuck jobs, exponential backoff, ownership-guarded terminal writes, DB-level tests). Foundational reliability before long jobs.
2. **Task 13.6 — Deploy/migration safety** (prod migration must be backup-gated; migration wait/retry). Data safety before more deploys.
3. **Task 18 — Admin seed command** → admin APIs usable so jobs can be driven without DB surgery.
4. **Task 14 — Real Miniflux sync sink + trigger** → 抓取 metadata works.
5. **Task 17 — Content-fetch job** → 正文抓取 works before expensive scoring.
6. **Task 15 — Real LLM provider + MiniMax (8-dim) + score sink + resilience** → 评分 works on usable content.
7. **Task 16 — Real recommendations sink** → Top10 works from active scores.
8. **Task 19 — Real MiniMax ask provider** → AI 辅助阅读 works.
9. **Task 20 — Frontend cutover** → users see all of it (write a dedicated plan first).

## 3. Guiding constraints (apply to every task)

- **TDD:** failing test → run → implement → green. `pytest` for api/worker, Node `--test` for web, co-located. Fakes for unit logic; gate real DB/LLM behind opt-in integration tests.
- **Cost control (hard rule, `DEPLOYMENT.md` §7):** CI and smoke **must never call a real LLM**. Default `LLM_PROVIDER=mock`; keep the CI mini-benchmark's `real_llm_calls == 0` assertion.
- **⚠️ Secrets:** `MINIMAX_API_KEY` and admin recovery codes are secrets — never logged, never echoed into `jobs.last_error`/`result` or request/answer logs (`SECURITY.md`). Providers **fail closed** when `LLM_PROVIDER=minimax` but key missing/`change_me`.
- **Resilience invariant (`SCORING_RUBRIC.md` §4):** one article's LLM failure → length-baseline row `scoring_status='error'`, `is_active=false`, excluded from ranking; never crash the batch.
- **Single source of truth:** B4 ranking stays in `apps/api/app/domain/ranking.py`; worker reuses via the existing path/importlib bridge while the monorepo ships together. `tier_for_score()` shared by contract; LLM never sets the tier.
- **Reuse:** port from `apps/scorer-worker/src/{llm_client,scoring,miniflux_client}.py` and `apps/reader-web/src/lib/articles/contentQuality.ts`. Keep old `apps/scorer-worker`/`apps/reader-web` data paths until Task 20 cutover is proven.
- **Precise edits:** no unrelated refactors; keep all api + worker tests green throughout; respect OpenAPI + typed-client drift gates when api routes change.

---

## Task 13.5 — Worker queue hardening (from post-Task-13 review)

**Goal:** Make the job engine survive worker crashes and transient dependency outages without stuck or double-processed jobs, and cover the Postgres state-machine SQL with a real DB test. None of this is cosmetic — it must land before Task 15's multi-second MiniMax jobs.

**Files:**
- Modify: `apps/worker/app/jobs/queue.py`
- Modify: `apps/worker/app/runner.py` / `apps/worker/app/main.py` (only if a periodic reclaim sweep belongs in the loop)
- Modify/extend: `apps/worker/tests/test_runner.py`; Create: `apps/worker/tests/test_queue_postgres.py`
- Possibly modify: `apps/api/app/db/repositories/jobs.py` (only if a shared reclaim query is cleaner there)

**Spec refs:** `ARCHITECTURE.md` §4 (state machine incl. `cancelled`), `DATA_MODEL.md` §jobs (`locked_at`, `max_attempts`, `run_after` backoff).

- [x] **Step 1: Stale `running` reclaim (review #2).** Failing test: a job left in `running` with `locked_at` older than a lease window is reclaimable and re-runs (respecting `max_attempts`); a fresh `running` job is **not** stolen. Implement: add `reclaim_stale(lease_seconds, *, base_backoff_seconds, max_backoff_seconds)` and call it before `claim_next` in the loop. Reclaim requeues `running` jobs whose `locked_at < NOW() - :lease`; `attempt_count` was already incremented at claim, so exhausted jobs become `failed`, otherwise `run_after` uses the same exponential backoff helper as normal retry. Lease via `WORKER_JOB_LEASE_SECONDS` (default 900). Keep the existing `claim_next` queued SELECT intact.
- [x] **Step 2: Ownership-guarded terminal writes (review #4).** Failing test: `mark_succeeded`/`mark_failed`/`mark_retryable_failure` only mutate a row that is still `status='running'` and `locked_by=:worker_id`; a row already reclaimed by another worker is left untouched (returns `None`). Implement: change queue method signatures to require `worker_id`, and add `AND status='running' AND locked_by=:worker_id` to Postgres terminal `UPDATE`s plus the InMemory equivalents. This makes completion idempotent and safe once Step 1 can reassign jobs.
- [x] **Step 3: Exponential backoff (review #3).** Failing test: retry `run_after` grows with `attempt_count` (`base * 2^(attempt_count-1)`) capped at `WORKER_RETRY_BACKOFF_MAX_SECONDS`. Implement one shared `retry_backoff_seconds(attempt_count, base_seconds, max_seconds)` helper used by InMemory, Postgres, normal retry, and stale reclaim. Keep `WORKER_RETRY_BACKOFF_SECONDS` as the base.
- [x] **Step 4: Postgres state-machine DB test (review #5).** Add `test_queue_postgres.py`; skip unless `WORKER_QUEUE_POSTGRES_TEST_URL` is set so local runs stay cheap. The test uses the API Alembic `0001` migration, enqueues via the API `JobStore`, then exercises the worker `PostgresJobQueue`: `claim_next` → `mark_retryable_failure` (retry and exhaustion branches) → `mark_succeeded`, asserting real row state through the `SELECT ... FOR UPDATE` path. This is the only coverage of the real SQL today.
- [x] **Step 5: `cancelled` state (review #6).** Implement queue-level `mark_cancelled(job_id, *, worker_id=None)` and tests that cancelled jobs are never claimed and terminal writes do not overwrite cancelled rows. Do **not** add an admin cancel endpoint in this task; record in `docs/learning-notes.md` that user/admin cancellation is deferred to a dedicated admin cancel-job feature.
- [x] **Step 6: Nits (review #8).** Move `import logging` to module top in `main.py`; add a small `JobQueue` Protocol (or typed param) for `run_once`/`run_forever`'s `queue` so the contract is explicit. No behavior change.
- [x] **Step 7: Verify** — worker pytest + ruff; `git diff --check`.
- [x] **Step 8: Commit** — `feat(worker): reclaim stale jobs and harden queue state machine`.

---

## Task 13.6 — Deploy / migration safety (from post-Task-13 review)

**Goal:** Auto-migration on deploy must not run against **prod** without a fresh backup, and must not fail the deploy because the API container is mid-start.

**Files:**
- Modify: `infra/scripts/deploy.sh`
- Modify: `infra/scripts/check-deploy-migrations.sh` (extend the guard for the prod backup gate)
- Tests: shell `bash -n` + the existing CI "Check deploy scripts" step; add an assertion to `check-deploy-migrations.sh`

**Spec refs:** `DEPLOYMENT.md` §5 (prod: `backup.sh prod` must succeed and emit artifact + sha256 **before** migration; never migrate/overwrite prod without backup), §6 (`backup.sh` exists: `pg_dump -Fc` + sha256).

- [x] **Step 1: Prod backup gate (review #1).** Failing guard/test: `check-deploy-migrations.sh` asserts deploy.sh runs `backup.sh "$ENV"` (or refuses) before `alembic upgrade head` **when `ENV=prod`**. Implement in deploy.sh: for `prod`, run `backup.sh prod` and abort the deploy if it fails (capture artifact path + sha256 into the workflow summary); for `staging`, keep auto-migrate as-is. Do **not** weaken the existing dirty-worktree guard.
- [x] **Step 2: Migration readiness (review #7).** Make `exec -T ai-reader-api alembic upgrade head` resilient to a not-yet-ready API/DB: a short bounded wait/retry (e.g. retry `alembic current` a few times, or `pg_isready`/`SELECT 1` against the data network) before upgrade. Fail loudly after the bound — never silently skip the migration.
- [x] **Step 3: Keep the order guard honest.** The `awk` in `check-deploy-migrations.sh` is intentionally string-coupled to deploy.sh wording; update it alongside any deploy.sh phrasing change so the regression guard keeps passing. Consider matching on a stable marker comment rather than full command text.
- [x] **Step 4: Verify** — `bash -n` on all scripts; `bash infra/scripts/check-deploy-migrations.sh`; compose still renders with `.env.example`; `git diff --check`.
- [x] **Step 5: Commit** — `fix(infra): gate prod migrations on backup and harden migrate step`.

---

## Task 18 — Admin seed command

**Goal:** `python -m app.seed create-admin` (`DATA_MODEL.md` §app_users) so an admin exists to drive scoring/jobs.

**Files:**
- Create: `apps/api/app/seed.py`
- Tests: `apps/api/tests/test_seed.py`

- [x] **Step 1: Failing test** — `create-admin --display-name X` inserts an `app_users` row with `role='admin'` and returns/prints a one-time recovery code; re-running is safe (no silent duplicate admin — require an explicit flag or detect existing).
- [x] **Step 2: Implement** with `argparse` mirroring `export_openapi.py`, reusing `DatabaseAuthStore.create_user(role="admin")`. ⚠️ Print the recovery code **once** to stdout; never log it elsewhere; never hardcode in a migration.
- [x] **Step 3: Verify + Commit** — `feat(api): add admin seed command`.

**Runbook note (not code):** document `docker compose ... exec ai-reader-api python -m app.seed create-admin --display-name "..."` in `docs/runbooks/`.

---

## Task 14 — Real Miniflux sync sink + trigger

**Goal:** `sync_miniflux_entries` actually pulls Miniflux entries and writes `articles` + `article_sources` to Postgres; provide a way to enqueue it.

**Files:**
- Create: `apps/worker/app/providers/miniflux.py` (HTTP client; port `apps/scorer-worker/src/miniflux_client.py`)
- Create: `apps/worker/app/db/article_sink.py` (DB-backed `ArticleSink` for `sync_miniflux.py`)
- Modify: `apps/worker/app/jobs/sync_miniflux.py` (register handler; keep pure transform), `apps/worker/app/main.py` (register `sync_miniflux_entries` handler)
- Modify: `apps/api/app/api/routes/admin.py` (add `POST /api/admin/sync` enqueuing `sync_miniflux_entries`)
- Tests: `apps/worker/tests/test_article_sink.py`, extend `test_sync_miniflux.py`, `apps/api/tests/test_admin.py`

**Spec refs:** `ARCHITECTURE.md` §5.3, `DATA_MODEL.md` §3 (dedup_key find/create → upsert `article_sources`), §2 (`article_sources` unique constraints).

- [x] **Step 1: Failing tests** — sink writes a new `articles` row when `dedup_key` is new, reuses the existing `articles.id` and only adds an `article_sources` row when `dedup_key` matches; `(feed_id, miniflux_entry_id)` upsert is idempotent; admin sync endpoint enqueues a job (202) and dedupes.
- [x] **Step 2: Port Miniflux client** — minimal read surface (list entries since cursor/limit). Prefer worker `MINIFLUX_API_KEY` when present; else Basic Auth via `MINIFLUX_USERNAME`/`MINIFLUX_PASSWORD` from compose. Test the auth-header selection so `.env.example` + compose stay aligned.
- [x] **Step 3: Implement DB `ArticleSink`** against the real schema (find-or-create by `dedup_key`, upsert sources, set `primary_feed_id` on first source, compute `content_hash`). Keep `canonicalize_url`/`TRACKING_PARAMS` consistent with `apps/api/.../articles.py` (already aligned).
- [x] **Step 4: Trigger** — `POST /api/admin/sync` (admin-gated) enqueues `sync_miniflux_entries`. Optional interval self-enqueue guarded by `SYNC_INTERVAL_SECONDS` (default off; scheduled is backup, manual primary).
- [x] **Step 5: Verify** — api + worker pytest + ruff; OpenAPI/typed-client drift gates (new admin route); `git diff --check`.
- [x] **Step 6: Commit** — `feat(worker): wire real Miniflux sync into articles and sources`.

---

## Task 17 — Content-fetch job (fetch_article_content)

**Goal:** Implement the missing `fetch_article_content` handler: Miniflux fetch-content (readability stage) → external provider → snippet fallback, with content-quality classification and the 7-day cache.

**Files:**
- Create: `apps/worker/app/jobs/fetch_content.py`, `apps/worker/app/content_quality.py` (port `apps/reader-web/src/lib/articles/contentQuality.ts` to Python), `apps/worker/app/providers/external_content.py` (pluggable `ExternalContentProvider`; `EXTERNAL_CONTENT_PROVIDER=none` default — **do not hardcode any single vendor**), `apps/worker/app/db/content_sink.py` (writer for `articles.content_*`, `fetched_at`, `content_expires_at`, `content_hash`)
- Modify: `apps/worker/app/main.py` (register handler), `apps/worker/app/providers/miniflux.py` (add fetch-content call)
- Tests: `apps/worker/tests/test_content_quality.py`, `test_fetch_content.py`

**Spec refs:** `ARCHITECTURE.md` §5.3, `DATA_MODEL.md` §4 (`content_quality` full/partial/snippet; `content_expires_at = fetched_at + 7 days`; never `published_at + 7d`). **Research finding:** reader-web does not extract text itself — it calls Miniflux `v1/entries/{id}/fetch-content`, then `decideFetchedArticleContent()` decides replace/keep (full ≥280 chars & no error-page patterns; replace only if ≥8% or ≥24 chars longer; reject "enable javascript / access denied / just a moment" pages). Port that logic exactly.

- [x] **Step 1: Failing tests** — quality classification (full/partial/snippet, error-page detection); replace-vs-keep heuristic; fallback chain readability→external(none)→snippet; writes `content_*` + `fetched_at` + `content_expires_at`.
- [x] **Step 2: Port `contentQuality` to Python**; implement provider chain + handler; sanitization stays in the `web` render layer (`ARCHITECTURE.md` §7) — worker stores raw + quality.
- [x] **Step 3: Verify + Commit** — `feat(worker): add article content fetch with quality fallback`.

---

## Task 15 — Real LLM provider factory + MiniMax (8-dim) + score sink + resilience

**Goal:** `score_batch` calls a real, configurable provider, writes full `article_base_scores` rows with active-history management, survives per-article failures, and chains into recommendations.

**Files:**
- Modify: `apps/worker/app/providers/llm.py` (port `MinimaxConfig.from_env` + `MinimaxLLMClient` from `apps/scorer-worker/src/llm_client.py`; add `create_provider()` factory; adapt prompt + parser from 7-dim to v0.4 **8-dim**)
- Modify: `apps/worker/pyproject.toml` (add `httpx>=0.27`)
- Create: `apps/worker/app/db/score_sink.py`
- Modify: `apps/worker/app/jobs/score_batch.py` (per-article try/except → baseline error row; enqueue `generate_recommendations` on completion)
- Shared `tier_for_score()`: a neutral module **only if** both packages import it without top-level `app` conflict; else duplicate the tiny helper in worker and add api/worker contract tests for the same 85/70/50 boundaries.
- Tests: `apps/worker/tests/test_llm_provider.py`, `test_score_sink.py`, extend `test_scoring.py`

**Spec refs:** `SCORING_RUBRIC.md` §1 (8 dims), §2 (`tier_for_score`), §3 (strict-JSON + `<think>` strip + `_extract_first_json_object`), §4 (baseline fallback), §6 (`MiniMaxProvider`: `POST {base_url}/chat/completions`, Bearer, `temperature=0.2`, 30s; `LLM_PROVIDER=minimax|mock`). `DATA_MODEL.md` §article_base_scores (partial unique `(article_id) WHERE is_active=true`; error rows `is_active=false`).

**Port reference (verbatim env/constants from old scorer-worker):** `MINIMAX_API_KEY` (fail if empty/`change_me`), `MINIMAX_BASE_URL` (default `https://api.minimax.io/v1`), `MINIMAX_MODEL` (default `MiniMax-M2.7`), `LLM_TIMEOUT_SECONDS` (default 30). Baseline = `min(100, len(combined)//50)`, `scoring_status='error'`, `model_provider='baseline'`, `reason='评分失败，需重新评分。'`. **Change vs old:** 8 v0.4 dims (`topic_relevance, information_density, source_quality, novelty, timeliness, actionability, reading_cost_fit, risk_uncertainty`); write target `article_base_scores`; `base_score` = LLM overall (not a dim average); tier from `tier_for_score`. Surface LLM/timeout failures inside the handler as the baseline path — raise `RetryableJobError` only for whole-batch infra failures (e.g. DB down), not per-article LLM errors.

- [x] **Step 1: Failing tests** — `create_provider("mock")` → `MockProvider`; `create_provider("minimax")` with no key → raises (fail-closed); 8-dim JSON parses + clamps; `<think>` stripped; malformed JSON → baseline `error`; `tier_for_score` boundaries. Score sink: success row sets `is_active=true` and flips prior active false (exactly one active per article); error row `is_active=false`; `scoring_batch_items.status`/`base_score_id` updated; batch status → `done`.
- [x] **Step 2: Provider factory + MiniMax client** — port client; build the 8-dim system prompt from the active rubric; reuse the existing `_strip_think_blocks`/`_extract_first_json_object` in `llm.py`.
- [x] **Step 3: DB `ScoreSink`** — write `article_base_scores` (all columns incl. `rubric_version`=active, `input_content_hash`, `confidence`, `risk_flags`), manage `is_active`, update batch items + batch.
- [x] **Step 4: Harden `score_batch`** — per-article try/except → baseline error row + item `error`, continue batch; on batch end enqueue `generate_recommendations` (dedupe per batch).
- [x] **Step 5: Verify** — api + worker pytest + ruff; CI mini-benchmark still `real_llm_calls==0`; `git diff --check`.
- [x] **Step 6: Commit** — `feat(worker): wire MiniMax scoring with 8-dim rubric and baseline fallback`.

---

## Task 16 — Real recommendations sink (generate_recommendations)

**Goal:** `generate_recommendations` selects candidates per spec, runs the existing `rank_b4`, and writes `recommendation_editions` + `recommendation_items` per user.

**Files:**
- Create: `apps/worker/app/db/recommendation_sink.py` (candidate query + edition/items writer)
- Modify: `apps/worker/app/jobs/generate_recommendations.py` (inject sink + reuse `rank_b4`), `apps/worker/app/main.py` (register handler)
- Tests: extend `apps/worker/tests/test_recommendations.py`

**Spec refs:** `SCORING_RUBRIC.md` §8 (window 3d→14d fallback; require `is_active=true && scoring_status='success'`; exclude `read/skipped`; dedup by `article_id`; subscription vs exploration; exploration `base_score>=80 && risk_uncertainty<=50`; top 8 + 2, backfill, no placeholders). `ARCHITECTURE.md` §5.5 (read-only editions; same input → same Top10).

- [x] **Step 1: Failing tests** — windowing (3d vs 14d fallback); exclusion of read/skipped and `duplicate && base_score<70`; subscription vs exploration partition; edition + items written with correct `rank`/`source`/`tier`/`rank_score`; deterministic order.
- [x] **Step 2: Implement sink** — candidate SQL + edition/items writes; call `rank_b4` (do not re-implement ranking).
- [x] **Step 3: Verify + Commit** — `feat(worker): generate Top10 recommendation editions`.

---

## Task 19 — Real MiniMax ask provider (SSE)

**Goal:** Replace `DeterministicAskProvider` with a real streaming MiniMax provider, selected by config, with deterministic fallback when unconfigured.

**Files:**
- Modify: `apps/api/app/api/routes/ask.py` (add `MiniMaxAskProvider`; keep `DeterministicAskProvider` fallback), `apps/api/app/main.py` (select by `LLM_PROVIDER`/key presence)
- Tests: extend `apps/api/tests/test_ask.py`

**Spec refs:** `ARCHITECTURE.md` §4 (ask is the **only** sync LLM path; no persistence), `SCORING_RUBRIC.md` §9, `SECURITY.md` (don't log bodies). `httpx` already in api deps.

- [x] **Step 1: Failing tests** — with `LLM_PROVIDER=minimax`+key, streams chunks (mock the HTTP stream) and `<think>` blocks stripped by the existing `stream_without_think_blocks`; with no key → `DeterministicAskProvider` fallback; prompt-injection defense + fixed Chinese sections preserved; no request/answer body logged.
- [x] **Step 2: Implement** streaming `chat/completions` with `stream=true`, reusing the SSE assembly + think-strip state machine; keep `MAX_ARTICLE_CONTEXT_CHARS`.
- [x] **Step 3: Verify + Commit** — `feat(api): add streaming MiniMax ask provider with deterministic fallback`.

---

## Task 20 — Frontend cutover to the new API (large; write its own plan first)

**Goal:** Point `apps/reader-web` at the new FastAPI backend so users see scoring/fetching/Top10/ask. **Biggest, least mechanical task — expand into a dedicated plan after Tasks 13.5–19 are proven on staging.**

**Why it's not a 1:1 swap:**
- reader-web's separate `read`/`star`/`read-later`/`project` routes → new API's unified `POST /api/articles/{id}/state` (`status` + `saved` + `read_progress`).
- reader-web browses by `module`/`sort` over Miniflux; new model centers on precomputed Top10 (`/api/recommendations/latest`) + `/api/articles` keyset list. Modules/feed-quality have no direct new endpoints yet.
- `/api/agent/article-chat` → `/api/articles/{id}/ask` (SSE).
- Auth: reader-web relied on the edge gateway; new model uses pseudo-login (`/api/auth/login` → cookie) — needs a login/identity UI.

**⚠️ Design decision (locked):** preserve the existing **warm-paper CSS-variable design** (`globals.css`, no Tailwind); swap only the data layer. The spec's "Tailwind/shadcn rebuild" note is superseded.

**Sub-phases (for the dedicated plan):** 20a typed client wrapper over `schema.ts` (fetch + cookie + SSE); 20b login/recover UI; 20c article list/detail + state actions; 20d home Top10 with score/tier/reason/risk ("Top 10 可解释"); 20e ask drawer (SSE) reusing `AgentMarkdown` + think-strip; 20f admin scoring-batch console; 20g decommission old reader-web/scorer-worker after parity.

**Dedicated plan:** `docs/superpowers/plans/2026-06-24-ai-reader-v04-frontend-cutover.md` (draft/ready after staging proof).

---

## Verification rollup (before any handoff)

```bash
git diff --check
cd apps/api    && uv run --isolated --with-editable . --extra dev python -m pytest tests -q && uv run --isolated --with-editable . --extra dev ruff check .
cd apps/worker && uv run --isolated --with-editable . --extra dev python -m pytest tests -q && uv run --isolated --with-editable . --extra dev ruff check .
# OpenAPI + typed client drift gates (when api routes change):
cd apps/api && uv run --isolated --with-editable . --extra dev python -m app.export_openapi --out openapi.json
npx --yes openapi-typescript@7.13.0 apps/api/openapi.json -o apps/reader-web/src/lib/api/generated/schema.ts
git diff --exit-code -- apps/api/openapi.json apps/reader-web/src/lib/api/generated/schema.ts
# deploy guards:
bash -n infra/scripts/deploy.sh infra/scripts/smoke-test.sh .github/scripts/remote-deploy.sh .github/scripts/validate-deploy-env.sh
bash infra/scripts/check-deploy-migrations.sh
```

When Docker/Postgres available: run the worker against a real DB once (claim → score with `LLM_PROVIDER=mock` → write rows → generate edition) as an integration smoke. **Never** run the real-MiniMax path in CI.

## Decisions locked for MVP (carried from Phase 1)

1. **Scheduler:** manual admin-trigger only; add scheduled backup after the manual path is proven.
2. **Frontend design:** preserve warm-paper CSS-variable design; swap data layer only.
3. **Worker concurrency:** single-loop (`WORKER_CONCURRENCY=1`).
4. **Task 20 packaging:** write its own cutover plan before starting.

## Reviewer decisions applied before execution

- **`cancelled` state (Task 13.5 Step 5):** implement the queue state-machine support now, but defer any admin cancel-job endpoint. This closes the worker state-machine gap without expanding the API surface during reliability hardening.
