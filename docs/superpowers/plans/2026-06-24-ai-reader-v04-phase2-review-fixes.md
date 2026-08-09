# AI Reader v0.4 Phase 2 — Review Fixes

> **For agentic workers:** Implement task-by-task with TDD. Steps use checkbox (`- [ ]`). These fixes come from the post-Phase-2 review of commits `e951d2e..09da827` (Tasks 13.5, 13.6, 18, 14, 17, 15, 16, 19). **Task F1 is a release blocker** — do it first. Keep all api + worker tests green and respect the OpenAPI/typed-client drift gates.
>
> **Status:** IMPLEMENTED locally. Postgres real-schema execution is wired into CI; this machine has no Docker/Postgres daemon, so the real Postgres guard is expected to run in CI or on a host with `WORKER_QUEUE_POSTGRES_TEST_URL`.
>
> **Deployment note (2026-08):** This is a historical implementation plan, not an execution runbook. Any old deployment workflow, SSH, GHCR, or `infra/scripts/*` snippet in this file is archived and must not be executed directly.

---

## Context

Phase 2 wired the real execution layer and all tests are green — but the sink unit tests run only against `sqlite:///:memory:` using a **hand-rolled schema** (`apps/worker/tests/test_recommendations.py:262,295` define `enabled INTEGER` / `is_active INTEGER`, JSONB as TEXT). That fake schema hides three places where the SQL is **invalid on the real PostgreSQL schema**, where `is_active`/`enabled` are `BOOLEAN` and the score columns are `JSONB`. Because `apps/worker/app/main.py` wires `_score_batch`/`_generate_recommendations` to the real sinks, the **scoring + Top10 pipelines are 0% functional on Postgres** despite green CI.

Reference implementation that already does this correctly: `apps/worker/app/db/article_sink.py` (branches on `engine.dialect.name == "postgresql"`, handles `ON CONFLICT ... DO NOTHING` empty `RETURNING`). The queue also already uses `CAST(:result AS jsonb)` (`apps/worker/app/jobs/queue.py`).

---

## Task F1 — Postgres-safe scoring & recommendation sinks (🔴 BLOCKER)

**Goal:** `score_batch` and `generate_recommendations` run successfully against the **real Alembic schema on PostgreSQL**, and a real-schema integration test prevents regression. Scoring writes and the Top10 candidate query must stop using integer literals for boolean columns and must cast JSON for JSONB columns.

**Files:**
- Modify: `apps/worker/app/db/score_sink.py`
- Modify: `apps/worker/app/db/recommendation_sink.py`
- Create: `apps/worker/tests/test_sinks_postgres.py` (skipped unless a Postgres URL env is set, mirroring `apps/worker/tests/test_queue_postgres.py`)
- Modify: `.github/workflows/ci.yml` (run the Postgres-backed worker tests against the existing `postgres` service)

**Spec refs:** `DATA_MODEL.md` §article_base_scores (`is_active BOOLEAN`, JSONB columns, partial unique `(article_id) WHERE is_active=true`), §user_feed_subscriptions (`enabled BOOLEAN`).

- [x] **Step 1: Root-cause failing test (real schema on Postgres).** Add `test_sinks_postgres.py`, skipped unless `WORKER_QUEUE_POSTGRES_TEST_URL` (reuse the same env as the queue test) is set. It must: run the API Alembic `0001` migration to build the **real** schema, seed a feed/subscription/article, then:
  - `DatabaseScoreSink.save_score` for a **success** row (assert exactly one `is_active=true` row per article; a second success flips the prior to false) and an **error** row (`scoring_status='error'`, `is_active=false`), asserting the JSONB columns (`dimension_scores`, `dimension_reasons`, `tags`, `risk_flags`) round-trip as JSON.
  - `DatabaseRecommendationSink._candidate_rows()` / `_user_priorities()` return the expected rows.
  This test **must fail on current code** (boolean/jsonb errors) before the fix.
- [x] **Step 2: Wire it into CI.** In `.github/workflows/ci.yml`, set `WORKER_QUEUE_POSTGRES_TEST_URL` (point at the existing `postgres:16` service) for the worker test step so both `test_queue_postgres.py` and `test_sinks_postgres.py` actually execute in CI, not just locally. Keep the local default skip so `npm`/offline runs stay cheap.
- [x] **Step 3: Fix booleans.** In `score_sink.py` (`save_score`, `_score_values`) and `recommendation_sink.py` (`_user_priorities` `enabled=1`, `_candidate_rows` `bs.is_active = 1`): bind Python `bool` values and compare with boolean literals (`WHERE is_active = TRUE` / `SET is_active = FALSE` / `WHERE enabled = TRUE`). `TRUE`/`FALSE` and bool binds work in both PostgreSQL and SQLite ≥3.23, so the existing fast tests stay valid. Do **not** keep any `= 1`/`= 0` against these columns.
- [x] **Step 4: Fix JSONB writes.** In `score_sink.py`, the four JSONB columns must be cast on insert. Use the dialect-aware approach already used in `article_sink.py` (branch on `engine.dialect.name`): PostgreSQL `CAST(:dimension_scores AS jsonb)` (etc.); SQLite keeps the plain `:param` (a `CAST(... AS jsonb)` in SQLite applies NUMERIC affinity and would corrupt the JSON string — do not use it on SQLite). Alternative the reviewer may prefer: bind via `sqlalchemy.text(...).bindparams(bindparam("dimension_scores", type_=JSONB))` so SQLAlchemy renders the cast per dialect.
- [x] **Step 5: Verify** — local SQLite worker tests and ruff passed; `test_sinks_postgres.py` defaults to skip locally and is wired to run in CI via `WORKER_QUEUE_POSTGRES_TEST_URL`.
- [x] **Step 6: Commit** — `fix(worker): make scoring and recommendation sinks Postgres-safe`.

**Decision for reviewer:** keep dual-dialect sinks (fast SQLite unit tests + Postgres integration test, as above) **or** drop SQLite for sinks and test only against Postgres. Recommended: keep dual-dialect (article_sink already is) and add the Postgres guard — SQLite-only tests gave false confidence here, so the Postgres test is mandatory either way.

---

## Task F2 — Sink correctness polish (🟡)

**Goal:** Fix timestamp timezone correctness and error-field hygiene surfaced in review.

**Files:**
- Modify: `apps/worker/app/db/score_sink.py`
- Modify: `apps/worker/app/jobs/score_batch.py`
- Optional: `apps/worker/app/main.py`

- [x] **Step 1: UTC timestamps.** `score_sink.py` uses naive `datetime.now().isoformat()` for `scored_at` and `finished_at` (TIMESTAMPTZ columns) — switch to `datetime.now(UTC)` (or SQL `NOW()`), matching `recommendation_sink.py` which already uses UTC. Failing test: a written `scored_at` is timezone-aware / equals the SQL `NOW()` path. Affects B4 `freshness_adjustment` correctness when the container TZ ≠ UTC.
- [x] **Step 2: Truncate baseline error.** `score_batch._baseline_error_score` stores `str(error)` unbounded; truncate to 240 chars like the legacy scorer (`apps/scorer-worker/src/scoring.py`). Test: a very long error message is capped. (Confirm no secret/API-key text can reach this field — current exceptions don't include the key, which lives in headers, but keep the truncation as defense.)
- [x] **Step 3 (optional): Engine reuse.** Skipped for MVP; per-job engine/pool churn is acceptable and changing handler lifetime would expand scope beyond the review fixes.
- [x] **Step 4: Verify + Commit** — `fix(worker): use UTC score timestamps and bound baseline error`.

---

## Task F3 — Harden the prod backup-gate parsing (🟡)

**Goal:** Make the prod migration backup gate not depend on scraping a localized log string.

**Files:**
- Modify: `infra/scripts/backup.sh` (emit a stable machine-readable marker), `infra/scripts/deploy.sh` (`run_prod_migration_backup` parsing)

**Context:** `deploy.sh:run_prod_migration_backup` extracts the backup dir via `sed -n 's/^✅ 备份完成：//p'` — coupled to `backup.sh`'s Chinese output text; a wording change silently breaks the parse (it fails closed and aborts the deploy, so it's safe but brittle).

- [x] **Step 1:** Have `backup.sh` print a stable, parseable line (e.g. `BACKUP_DIR=<abs-path>` and `BACKUP_SHA256_FILE=<path>`) in addition to the human-readable message.
- [x] **Step 2:** Parse that marker in `deploy.sh` instead of the emoji/Chinese string; keep the existing fail-closed behavior and the `GITHUB_STEP_SUMMARY` artifact reporting.
- [x] **Step 3:** Update `check-deploy-migrations.sh` only if its string assertions need to match new wording; keep the order guard (backend up → backup → ready → migrate → authelia) intact.
- [x] **Step 4: Verify + Commit** — `fix(infra): parse backup artifact via stable marker in prod gate`.

---

## Verification rollup

```bash
git diff --check
cd apps/api    && uv run --isolated --with-editable . --extra dev python -m pytest tests -q && uv run --isolated --with-editable . --extra dev ruff check .
cd apps/worker && uv run --isolated --with-editable . --extra dev python -m pytest tests -q && uv run --isolated --with-editable . --extra dev ruff check .
# Real-schema guard (the point of F1) — must pass once fixed:
WORKER_QUEUE_POSTGRES_TEST_URL=postgres://postgres:postgres@localhost:5432/postgres \
  uv --directory apps/worker run --isolated --with-editable . --extra dev python -m pytest tests/test_sinks_postgres.py tests/test_queue_postgres.py -q
# deploy guards:
bash -n infra/scripts/deploy.sh infra/scripts/backup.sh infra/scripts/smoke-test.sh
bash infra/scripts/check-deploy-migrations.sh
```

## What was already correct (do not change)

`article_sink.py` (dialect-aware, handles empty `RETURNING`); queue hardening (reclaim/ownership-guard/exponential backoff/cancelled); Task 13.6 prod backup gate + migration-readiness retry; Task 19 ask provider (fail-closed, graceful deterministic fallback, no body logging, SSE delta/`[DONE]` parsing); Task 18 admin seed (`admin_exists()` guard, one-time recovery code to stdout); Task 15 provider factory + per-article baseline resilience.

## Priority

- **F1 = blocker:** must land (and the Postgres CI test must run green) before this branch is merged or staging is trusted for scoring/Top10.
- **F2, F3 = follow-ups:** correctness/robustness; can land in the same PR or immediately after.
