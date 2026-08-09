# AI Reader v0.4 Runtime Activation Plan

> SUPERSEDED by `2026-06-24-ai-reader-v04-completion-roadmap.md` on 2026-06-24 — historical reference only. Deployment commands and workflow examples in this file are archived; do not execute them directly.

> **For agentic workers:** Implement task-by-task with TDD. Steps use checkbox (`- [ ]`) syntax for tracking. Read `docs/spec/ARCHITECTURE.md` §4–§8, `docs/spec/DATA_MODEL.md`, `docs/spec/SCORING_RUBRIC.md`, `docs/spec/DEPLOYMENT.md` before coding. Reuse-not-rewrite: port proven logic from `apps/scorer-worker` and `apps/reader-web`, don't reinvent.

**Status of this doc:** DESIGN ONLY. Author = review pass after Tasks 1–12 (v0.4 contract + skeleton + delivery pipeline) merged. To be reviewed by Codex before any implementation.

---

## 1. Why this phase exists

The v0.4 plan (`2026-06-23-ai-reader-v04-refactor.md`, Tasks 1–12) is **fully complete**: it delivered the HTTP contract, Alembic schema, B4 ranking algorithm, OpenAPI + typed client, containerization, CI, and staging deploy. By design it stopped at a **contract + skeleton**: Protocol sinks, `MockProvider`/`DeterministicAskProvider`, and "preserve frontend".

Nothing yet **runs end-to-end with real data, a real LLM, or the real UI**. This plan wires the execution layer so the three product capabilities actually work:

| Capability | Contract done | Execution missing |
|---|---|---|
| **评分 Scoring** | batch APIs, `article_base_scores` DDL, B4 | worker loop, real MiniMax provider, DB score sink, resilience, admin seed |
| **抓取 Fetching** | Miniflux sync pure-fn, feeds API, `articles`/`article_sources` DDL | worker loop, real sync sink, scheduler, **content-fetch job (none exists)** |
| **AI 辅助阅读 Ask** | SSE pipeline, prompt-injection defense, `<think>` strip, fixed sections | real MiniMax streaming provider (currently returns a "模型未配置" placeholder) |

**Schema is already complete** — `jobs` has `attempt_count/max_attempts/run_after/completed_at/last_error/result/progress/locked_by`, `article_base_scores` has all 8-dim/tier/status/is_active columns, and categories + rubric v1 are seeded in `0001_initial.py`. **This phase adds no migrations** (except code, not schema). The work is wiring.

## 2. The unlock order (why this sequence)

A, B/H, C are shared blockers — building the worker runtime once lights up scoring, sync, and recommendations together. Order minimizes rework:

1. **Task 13 — Worker runtime loop + job state machine + deploy liveness** (THE unlock; everything else is a handler on top).
2. **Task 18 — Admin seed command** → admin APIs become usable so jobs can be driven without DB surgery.
3. **Task 14 — Real Miniflux sync sink + trigger** → 抓取 metadata works.
4. **Task 17 — Content-fetch job** → 正文抓取 works before expensive scoring.
5. **Task 15 — Real LLM provider factory + MiniMax (8-dim) + score sink + resilience** → 评分 works on usable content.
6. **Task 16 — Real recommendations sink** → Top10 works from active scores.
7. **Task 19 — Real MiniMax ask provider** → AI 辅助阅读 works.
8. **Task 20 — Frontend cutover** → users actually see all of it (large; write a dedicated plan first).

Implement in this unlock order even though existing task numbers stay stable for references.

## 3. Guiding constraints (apply to every task)

- **TDD:** write failing test → run → implement → green. Tests are Node-style for web, `pytest` for api/worker, co-located. Use fakes for unit logic; gate real DB/LLM behind opt-in integration tests.
- **Cost control (hard rule, `DEPLOYMENT.md` §7):** CI and smoke-test **must never call a real LLM**. Default `LLM_PROVIDER=mock`; MiniMax only when explicitly configured. The CI mini-benchmark already asserts `real_llm_calls == 0` — keep that property.
- **⚠️ Secrets:** `MINIMAX_API_KEY` and admin recovery codes are secrets. Never log them, never print request/answer bodies (`SECURITY.md`). Provider must **fail closed** when `LLM_PROVIDER=minimax` but key is missing or `change_me`.
- **Resilience invariant (`SCORING_RUBRIC.md` §4):** a single article's LLM failure must produce a length-baseline row with `scoring_status='error'`, `is_active=false`, excluded from ranking — never crash the whole batch.
- **Single source of truth:** B4 ranking stays in `apps/api/app/domain/ranking.py`. Worker must not import the API package as top-level `app` directly; keep the current explicit path/importlib bridge while the monorepo ships together, or move B4 into a real neutral shared package before splitting images. `tier_for_score()` is shared by contract; LLM never sets the tier.
- **Reuse:** port from `apps/scorer-worker/src/{llm_client,scoring}.py` and `apps/reader-web/src/lib/articles/contentQuality.ts`. Do not delete the old `apps/scorer-worker` / `apps/reader-web` data paths until Task 20 cutover is proven.
- **Precise edits:** no unrelated refactors; keep all 66 api + 22 worker tests green throughout.

---

## Task 13 — Worker runtime loop + job state machine + deploy liveness

**Goal:** A running worker that claims jobs, dispatches by `job_type`, and drives the `queued→running→succeeded/failed/cancelled` state machine with retry/backoff. This is the engine; later tasks register handlers.

**Files:**
- Modify: `apps/worker/app/jobs/queue.py` (add completion/failure/requeue methods to `PostgresJobQueue` + `InMemoryJobQueue`)
- Create: `apps/worker/app/runner.py` (dispatcher + run loop)
- Modify: `apps/worker/app/main.py` (build queue + registry, run loop, `__main__` entry)
- Modify: `infra/compose/docker-compose.base.yml`, `infra/scripts/deploy.sh`, `infra/scripts/smoke-test.sh` as needed so the worker starts on staging and smoke checks liveness
- Create: `apps/worker/tests/test_runner.py`

**Spec refs:** `ARCHITECTURE.md` §4 (state machine: succeeded/failed/retryable/cancelled), `DATA_MODEL.md` §jobs (`max_attempts` default 5; retry → `status='queued'`, `run_after=NOW()+backoff`; exhausted → `failed`+`completed_at`).

- [x] **Step 1: Write failing runner/state-machine tests** (`InMemoryJobQueue`-backed): claim→success marks `succeeded` + `result`; handler raising a retryable error requeues with `run_after` backoff and `attempt_count++`; at `max_attempts` → `failed` + `last_error` + `completed_at`; unknown `job_type` → `failed` (not crash); a non-retryable error fails immediately; empty queue → loop sleeps, no busy-spin.
- [x] **Step 2: Add queue methods** to both queues: extend worker `QueueJob` to mirror API `JobRecord` fields needed by the state machine (`max_attempts`, `result`, `completed_at`, `last_error`), then add `mark_succeeded(job_id, result)`, `mark_retryable_failure(job_id, error, backoff_seconds)`, and `mark_failed(job_id, error)`. Retry methods own the `attempt_count >= max_attempts` decision. Postgres versions use parameterized `UPDATE`. Keep the existing `claim_next` SQL untouched.
- [x] **Step 3: Implement `runner.py`**: a `HANDLERS: dict[str, Handler]` registry; `run_once(queue, registry, worker_id)` claims one job, dispatches, marks terminal/retry; `run_forever(...)` loops with idle sleep (poll interval env, e.g. `WORKER_POLL_SECONDS` default 2) and respects a stop signal (SIGTERM → graceful). `WORKER_CONCURRENCY` starts at 1 (single loop); document that >1 is a future enhancement.
- [x] **Step 4: Wire `main.py`**: build queue (`create_worker_queue()`), build registry (handlers added in later tasks; start with a no-op/echo handler for smoke-safe jobs), and under `if __name__ == "__main__": run_forever(...)`. Confirm `python -m app.main` now blocks and processes, not exits.
- [x] **Step 5: Activate worker in deployment** — either remove `profiles: [worker]` from the worker service or restore `--profile worker` in deploy. Pick one, document it, and add smoke-test liveness (container running/log heartbeat only; no HTTP and no LLM).
- [x] **Step 6: Verify** — worker pytest + ruff green; compose renders with `.env.example`; shell scripts parse; `git diff --check`.
- [x] **Step 7: Commit** — `feat(worker): add job runner loop and state machine`.

**Note for reviewer:** decide retryable-vs-fatal taxonomy here (e.g., `RetryableJobError` base class). Handlers raise it for transient failures (timeouts, 5xx); everything else is fatal.

---

## Task 14 — Real Miniflux sync sink + trigger

**Goal:** `sync_miniflux_entries` actually pulls Miniflux entries and writes `articles` + `article_sources` to Postgres; provide a way to enqueue it.

**Files:**
- Create: `apps/worker/app/providers/miniflux.py` (HTTP client; port `apps/scorer-worker/src/miniflux_client.py`)
- Create: `apps/worker/app/db/article_sink.py` (DB-backed `ArticleSink` for `sync_miniflux.py`)
- Modify: `apps/worker/app/jobs/sync_miniflux.py` (register handler; keep pure transform)
- Modify: `apps/worker/app/main.py` (register `sync_miniflux_entries` handler)
- Create/Modify: `apps/api/app/api/routes/admin.py` (add `POST /api/admin/sync` enqueuing `sync_miniflux_entries`)
- Tests: `apps/worker/tests/test_article_sink.py`, extend `test_sync_miniflux.py`, `apps/api/tests/test_admin.py`

**Spec refs:** `ARCHITECTURE.md` §5.3, `DATA_MODEL.md` §3 (dedup_key find/create → upsert `article_sources`), §2 (`article_sources` unique constraints).

- [ ] **Step 1: Failing tests** — sink writes a new `articles` row when `dedup_key` is new, reuses the existing `articles.id` and only adds an `article_sources` row when `dedup_key` matches; `(feed_id, miniflux_entry_id)` upsert is idempotent; admin sync endpoint enqueues a job (202) and dedupes.
- [ ] **Step 2: Port Miniflux client** — minimal read surface needed: list entries since cursor/limit. Prefer worker-specific `MINIFLUX_API_KEY` when present; otherwise fall back to Basic Auth using `MINIFLUX_USERNAME`/`MINIFLUX_PASSWORD` from compose. Add tests for auth-header selection so `.env.example` and compose stay aligned.
- [ ] **Step 3: Implement DB `ArticleSink`** against the real schema (find-or-create by `dedup_key`, upsert sources, set `primary_feed_id` on first source, compute `content_hash`). Keep `canonicalize_url`/`TRACKING_PARAMS` consistent with `apps/api/.../articles.py` (already aligned).
- [ ] **Step 4: Trigger** — `POST /api/admin/sync` (admin-gated) enqueues `sync_miniflux_entries`. Add an **optional** interval self-enqueue in the worker loop guarded by env (`SYNC_INTERVAL_SECONDS`, default off) — spec says scheduled is backup, manual is primary.
- [ ] **Step 5: Verify** — api + worker pytest + ruff; `git diff --check`.
- [ ] **Step 6: Commit** — `feat(worker): wire real Miniflux sync into articles and sources`.

---

## Task 15 — Real LLM provider factory + MiniMax (8-dim) + score sink + resilience

**Goal:** `score_batch` calls a real, configurable provider, writes full `article_base_scores` rows with active-history management, survives per-article failures, and chains into recommendations.

**Files:**
- Modify: `apps/worker/app/providers/llm.py` (port `MinimaxConfig.from_env` + `MinimaxLLMClient` from `apps/scorer-worker/src/llm_client.py`; add `create_provider()` factory; adapt the scoring prompt + parser from 7-dim to the v0.4 **8-dim** rubric)
- Modify: `apps/worker/pyproject.toml` (add `httpx>=0.27`)
- Create: `apps/worker/app/db/score_sink.py` (DB-backed `ScoreSink`)
- Modify: `apps/worker/app/jobs/score_batch.py` (per-article try/except → baseline error row; enqueue `generate_recommendations` on completion)
- Create: a neutral shared scoring module **only if** both packages can import it without top-level `app` conflicts; otherwise duplicate the tiny `tier_for_score()` helper in worker and add API/worker contract tests for the same 85/70/50 boundaries.
- Tests: `apps/worker/tests/test_llm_provider.py`, `test_score_sink.py`, extend `test_scoring.py`

**Spec refs:** `SCORING_RUBRIC.md` §1 (8 dims), §2 (`tier_for_score`), §3 (strict-JSON contract + `<think>` strip + `_extract_first_json_object`), §4 (baseline fallback), §6 (`MiniMaxProvider`: `POST {base_url}/chat/completions`, Bearer, `temperature=0.2`, 30s; `LLM_PROVIDER=minimax|mock`). `DATA_MODEL.md` §article_base_scores (partial unique `(article_id) WHERE is_active=true`; error rows `is_active=false`).

**Port reference (from old scorer-worker, verbatim env/constants):** `MINIMAX_API_KEY` (fail if empty or `change_me`), `MINIMAX_BASE_URL` (default `https://api.minimax.io/v1`), `MINIMAX_MODEL` (default `MiniMax-M2.7`), `LLM_TIMEOUT_SECONDS` (default 30). Baseline = `min(100, len(combined)//50)`, `scoring_status='error'`, `model_provider='baseline'`, `reason='评分失败，需重新评分。'`. **Change vs old:** dimensions become the 8 v0.4 keys (`topic_relevance, information_density, source_quality, novelty, timeliness, actionability, reading_cost_fit, risk_uncertainty`), write target is `article_base_scores`, and `base_score` is the LLM's overall (not a dim average); tier from `tier_for_score`.

- [ ] **Step 1: Failing tests** — `create_provider("mock")` → `MockProvider`; `create_provider("minimax")` with no key → raises (fail-closed); 8-dim JSON parses + clamps; `<think>` stripped; malformed JSON → baseline `error`; `tier_for_score` boundaries (85/70/50). Score sink: success row sets `is_active=true` and flips prior active to false (exactly one active per article); error row `is_active=false`; `scoring_batch_items.status`/`base_score_id` updated; batch status → `done`.
- [ ] **Step 2: Provider factory + MiniMax client** — port client; build the 8-dim system prompt from the active rubric; reuse the already-present `_strip_think_blocks`/`_extract_first_json_object` in the new `llm.py`.
- [ ] **Step 3: DB `ScoreSink`** — write `article_base_scores` (all columns incl. `rubric_version` = active version, `input_content_hash`, `confidence`, `risk_flags`), manage `is_active`, update batch items + batch.
- [ ] **Step 4: Harden `score_batch`** — wrap each article in try/except; on failure write baseline error row and mark the item `error`, continue the batch; on batch end enqueue `generate_recommendations` (dedupe per batch).
- [ ] **Step 5: Verify** — api + worker pytest + ruff; CI mini-benchmark still `real_llm_calls==0`; `git diff --check`.
- [ ] **Step 6: Commit** — `feat(worker): wire MiniMax scoring with 8-dim rubric and baseline fallback`.

---

## Task 16 — Real recommendations sink (generate_recommendations)

**Goal:** `generate_recommendations` selects candidates per spec, runs the existing `rank_b4`, and writes `recommendation_editions` + `recommendation_items` for each user.

**Files:**
- Create: `apps/worker/app/db/recommendation_sink.py` (candidate query + edition/items writer)
- Modify: `apps/worker/app/jobs/generate_recommendations.py` (inject sink + reuse `rank_b4`)
- Modify: `apps/worker/app/main.py` (register handler)
- Tests: extend `apps/worker/tests/test_recommendations.py`

**Spec refs:** `SCORING_RUBRIC.md` §8 (candidate window 3d→14d fallback; require `is_active=true && scoring_status='success'`; exclude `read/skipped`; dedup by `article_id`; subscription vs exploration split; exploration `base_score>=80 && risk_uncertainty<=50`; top 8 + 2, backfill, no placeholders). `ARCHITECTURE.md` §5.5 (read-only editions; same input → same Top10).

- [ ] **Step 1: Failing tests** — candidate windowing (3d vs 14d fallback); exclusion of read/skipped and `duplicate && base_score<70`; subscription vs exploration partition; edition + 1..N items written with correct `rank`/`source`/`tier`/`rank_score`; deterministic order.
- [ ] **Step 2: Implement sink** — the SQL candidate query and the edition/items writes; call `rank_b4` (do not re-implement ranking).
- [ ] **Step 3: Verify + Commit** — `feat(worker): generate Top10 recommendation editions`.

---

## Task 17 — Content-fetch job (fetch_article_content)

**Goal:** Implement the missing `fetch_article_content` handler: Miniflux fetch-content (readability stage) → external provider → snippet fallback, with content-quality classification and the 7-day cache.

**Files:**
- Create: `apps/worker/app/jobs/fetch_content.py` (handler)
- Create: `apps/worker/app/content_quality.py` (port `apps/reader-web/src/lib/articles/contentQuality.ts` to Python)
- Create: `apps/worker/app/providers/external_content.py` (pluggable `ExternalContentProvider`; `EXTERNAL_CONTENT_PROVIDER=none` default — **do not hardcode any single vendor**)
- Create: `apps/worker/app/db/content_sink.py` (DB-backed writer for `articles.content_*`, `fetched_at`, `content_expires_at`, `content_hash`)
- Modify: `apps/worker/app/main.py` (register handler), `apps/worker/app/providers/miniflux.py` (add fetch-content call)
- Tests: `apps/worker/tests/test_content_quality.py`, `test_fetch_content.py`

**Spec refs:** `ARCHITECTURE.md` §5.3, `DATA_MODEL.md` §4 (`content_quality` full/partial/snippet; `content_expires_at = fetched_at + 7 days`; never `published_at + 7d`). **Research finding:** reader-web does not extract text itself — it calls Miniflux `v1/entries/{id}/fetch-content`, then `decideFetchedArticleContent()` decides replace/keep (full ≥280 chars & no error-page patterns; replace only if ≥8% or ≥24 chars longer; reject "enable javascript / access denied / just a moment" pages). Port that decision logic exactly.

- [ ] **Step 1: Failing tests** — quality classification (full/partial/snippet, error-page detection); replace-vs-keep heuristic; fallback chain readability→external(none)→snippet; writes `content_*` fields + `fetched_at` + `content_expires_at`.
- [ ] **Step 2: Port `contentQuality` to Python**; implement provider chain + handler; sanitization stays in `web` render layer (per `ARCHITECTURE.md` §7) — worker stores raw + quality.
- [ ] **Step 3: Verify + Commit** — `feat(worker): add article content fetch with quality fallback`.

---

## Task 18 — Admin seed command

**Goal:** Provide the `python -m app.seed create-admin` command (`DATA_MODEL.md` §app_users) so an admin exists to drive scoring/jobs.

**Files:**
- Create: `apps/api/app/seed.py`
- Tests: `apps/api/tests/test_seed.py`

- [ ] **Step 1: Failing test** — `create-admin --display-name X` inserts an `app_users` row with `role='admin'` and returns/prints a one-time recovery code; re-running is safe (no duplicate admin silently created — require explicit flag or detect existing).
- [ ] **Step 2: Implement** with `argparse` mirroring `export_openapi.py`. ⚠️ Print the recovery code **once** to stdout; never log it elsewhere; never hardcode in a migration.
- [ ] **Step 3: Verify + Commit** — `feat(api): add admin seed command`.

**Runbook note (not code):** document `docker compose ... exec ai-reader-api python -m app.seed create-admin --display-name "..."` in `docs/runbooks/`.

---

## Task 19 — Real MiniMax ask provider (SSE)

**Goal:** Replace the `DeterministicAskProvider` placeholder with a real streaming MiniMax provider, selected by config, with deterministic fallback when unconfigured.

**Files:**
- Modify: `apps/api/app/api/routes/ask.py` (add `MiniMaxAskProvider`; keep `DeterministicAskProvider` as fallback)
- Modify: `apps/api/app/main.py` (select provider by `LLM_PROVIDER`/key presence)
- Tests: extend `apps/api/tests/test_ask.py`

**Spec refs:** `ARCHITECTURE.md` §4 (ask is the **only** sync LLM path; no persistence), `SCORING_RUBRIC.md` §9, `SECURITY.md` (don't log bodies). `httpx` already in api deps.

- [ ] **Step 1: Failing tests** — with `LLM_PROVIDER=minimax`+key, the provider streams chunks (mock the HTTP stream) and `<think>` blocks are stripped by the existing `stream_without_think_blocks`; with no key it falls back to `DeterministicAskProvider`; prompt-injection defense + fixed Chinese sections preserved; no request/answer body is logged.
- [ ] **Step 2: Implement** streaming `chat/completions` with `stream=true`, reusing the existing SSE assembly + think-strip state machine. Keep the server-side context cap (`MAX_ARTICLE_CONTEXT_CHARS`).
- [ ] **Step 3: Verify + Commit** — `feat(api): add streaming MiniMax ask provider with deterministic fallback`.

---

## Task 20 — Frontend cutover to the new API (large; likely its own plan)

**Goal:** Point `apps/reader-web` at the new FastAPI backend so users see scoring/fetching/Top10/ask. **This is the biggest, least mechanical task and should get its own detailed plan after Tasks 13–19 are proven on staging.**

**Why it's not a 1:1 swap (research finding):** the new API's model differs from reader-web's:
- reader-web has separate `read` / `star` / `read-later` / `project` routes → new API unifies these into `POST /api/articles/{id}/state` (`status` + `saved` + `read_progress`). The UI's four actions must map onto one state model (e.g. star/read-later → `saved`, project → annotation/`saved`).
- reader-web browses by `module`/`sort` over Miniflux; the new model centers on **precomputed Top10** (`/api/recommendations/latest`) + `/api/articles` keyset list. Modules/feed-quality have no direct new endpoints yet.
- reader-web's `/api/agent/article-chat` → new `/api/articles/{id}/ask` (SSE).
- Auth: reader-web relied on the edge gateway; the new model uses the API's pseudo-login (`/api/auth/login` → cookie). A login/identity UI is needed.

**⚠️ Design decision to confirm with the user:** `ARCHITECTURE.md` §7 / `FRONTEND.md` §8 say "migrate components to Tailwind/shadcn", but the user already chose and built a **warm-paper CSS-variable design (no Tailwind)** in `globals.css`. Recommendation: **preserve the existing warm-paper design**, swap only the data layer, and treat the spec's Tailwind note as superseded. Do not silently rebuild the UI.

**Suggested sub-phases (to expand into a dedicated plan):**
- [ ] 20a: Generate a typed API client wrapper over `src/lib/api/generated/schema.ts` (fetch + cookie + SSE helpers).
- [ ] 20b: Identity: login/recover UI using `/api/auth/*`; gate business pages.
- [ ] 20c: Article list + detail from `/api/articles*`; state actions onto `/state`.
- [ ] 20d: Home Top10 from `/api/recommendations/latest` with score/tier/reason/risk display (`ARCHITECTURE.md` §1 "Top 10 可解释").
- [ ] 20e: Ask drawer on `/api/articles/{id}/ask` (SSE) reusing the existing `AgentMarkdown` + think-strip render.
- [ ] 20f: Admin: scoring-batch console on `/api/admin/*`.
- [ ] 20g: Decommission old reader-web data paths + old `apps/scorer-worker` only after parity is verified.

---

## Verification rollup (run before any handoff)

```bash
git diff --check
cd apps/api    && uv run --isolated --with-editable . --extra dev python -m pytest tests -q && uv run --isolated --with-editable . --extra dev ruff check .
cd apps/worker && uv run --isolated --with-editable . --extra dev python -m pytest tests -q && uv run --isolated --with-editable . --extra dev ruff check .
# OpenAPI + typed client drift gates (if api routes changed):
cd apps/api && uv run --isolated --with-editable . --extra dev python -m app.export_openapi --out openapi.json
npx --yes openapi-typescript@7.13.0 apps/api/openapi.json -o apps/reader-web/src/lib/api/generated/schema.ts
git diff --exit-code -- apps/api/openapi.json apps/reader-web/src/lib/api/generated/schema.ts
```

When Docker/Postgres available: run the worker against a real DB once (claim → score with `LLM_PROVIDER=mock` → write rows → generate edition) as an integration smoke. **Never** run the real-MiniMax path in CI.

## Deployment acceptance gates (owned by Task 13)

- [ ] Worker starts on staging by default through the chosen compose/deploy path.
- [ ] `smoke-test.sh` checks worker liveness only — container running and logs/heartbeat if available. Keep smoke LLM-free.
- [ ] Set `LLM_PROVIDER=mock` in staging until MiniMax cost is intended; flip to `minimax` deliberately with the key set.

## Decisions locked for MVP

1. **Scheduler:** manual admin-trigger only for MVP. Add scheduled backup after the manual path is proven.
2. **Frontend design:** preserve warm-paper CSS-variable design and swap the data layer; do not rebuild with Tailwind/shadcn in this phase.
3. **Worker concurrency:** single-loop (`WORKER_CONCURRENCY=1`) for MVP.
4. **Task 20 packaging:** write a dedicated frontend cutover plan before starting because API state mapping and auth are large enough to deserve their own review.
