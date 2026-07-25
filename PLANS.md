# Project Optimization Execution Plan

> Authoritative goal: `GOAL.md`
> Updated: 2026-07-26 (Asia/Taipei)
> Behavior checkpoint: `29799d526297114a604da2eea1402c59dfcc21b5` (based on merged `main` `49b2ecf2445f7995488e9a7c25346f4e4989ce8b`)
> Current state: **M1 — core-loop truth and knowledge integrity, A-02/A-07 in progress**

## Execution Contract

- `GOAL.md` is authoritative for objective, MUST gates, non-goals, and completion. This file is only the current execution ledger.
- Work on one measurable bottleneck at a time. Begin with the smallest failing test or baseline, retain only complexity that improves a named acceptance row, and commit a reversible slice.
- No human response is required to continue. Missing infrastructure is replaced in priority order by a deterministic fixture, in-memory adapter, Mock, disposable local service, then CI service; missing external proof remains explicit rather than becoming a pass.
- Production, DNS, credentials, irreversible data operations, and real-provider spend remain outside autonomous mutation. Staging and synthetic/local evidence are the delivery boundary.
- Every durable behavior/process change updates `docs/learning-notes.md`; synthetic/redacted evidence is hashed in `output/evidence-sha256.txt`.

## Current Checkpoint

| Field | Current evidence |
| --- | --- |
| Exact candidate | Committed behavior checkpoint `29799d526297114a604da2eea1402c59dfcc21b5`; this ledger-only follow-up adds no runtime change |
| Milestone / acceptance | M1.2 Reader/Ask transient-failure continuity; A-02, A-07, and A-15 remain `IN_PROGRESS` |
| Hypothesis | A failing Ask request must not hide the active article; retrying the same action should return a grounded cited answer without requiring a real provider. |
| Initial failure | New Playwright scenario failed because the E2E proxy had no Ask failure/SSE contract. |
| Minimal repair | One-time typed Ask 503 fixture plus a deterministic SSE text/citation response. |
| Green validation | Focused Chromium 1/1; `npm test` 189/189; `npm run build`; `npm run test:e2e` 47/47. |
| Durable evidence | `output/evidence/m1-reader-ask-retry-2026-07-26.json`, integrity-listed in `output/evidence-sha256.txt` |
| Rollback | Revert this fixture/E2E slice; no production endpoint, schema, data, dependency, provider setting, or real-provider spend. |
| Next action | M1.3: choose the highest-value uncovered Keep/annotation or Review/Research/Export state from the A-02 matrix, beginning with deterministic fixture inventory and a failing test. |

## Completed Checkpoints

| Checkpoint | Acceptance advanced | Evidence | Remaining boundary |
| --- | --- | --- | --- |
| M0 baseline and evaluation infrastructure | A-01 | Versioned performance/security/Playwright artifacts and verified hash manifest | External browser/PostgreSQL route values remain `NEEDS_BASELINE` |
| Deterministic lint, self-hosted fonts, dependency/security and metrics boundary | A-01, A-04, A-11, A-12, A-15 | Exact-SHA CI/staging proof, pinned tooling, source/license artifacts, internal metrics/public deny | Rollback/registry cleanup and external-only evidence remain |
| Versioned annotation anchor | A-03, A-04, A-08 | API/OpenAPI/Reader/browser anchor tests | Refresh, repeated-quote, alternate input and session matrix incomplete |
| M1.1 Daily partial failure | A-02, A-07 | One failing test before repair; focused and full Reader validation after repair | One deterministic state slice only; full state/browser/input matrix incomplete |
| M1.2 Reader/Ask partial failure | A-02, A-07, A-15 | One failing test before repair; 503 → retry → SSE citation and full Reader validation | One deterministic Ask failure slice only; provider/recovery/state matrix incomplete |

## Acceptance Ledger

| ID | Status | Current proof / next necessary proof |
| --- | --- | --- |
| A-01 | PASS | Exact revision, evidence manifest, reproducible focused gates |
| A-02 | IN_PROGRESS | Daily Cluster partial-failure/retry/open-return and Reader/Ask 503→retry→citation slices green; complete Daily/Scan → Reader/Ask → Keep → Review/Research/Export state matrix remains |
| A-03 | IN_PROGRESS | Initial versioned anchor green; ambiguity, refresh, retry, touch-equivalent, keyboard and identity cases remain |
| A-04 | IN_PROGRESS | Admin/public metrics/session checks exist; two-user browser/cache matrix remains |
| A-05 | IN_PROGRESS | Known contrast gaps; automated audit, keyboard/reflow/reduced-motion proof remain |
| A-06 | IN_PROGRESS | Chromium subset green; six widths, Firefox/WebKit and input pairwise matrix remain |
| A-07 | IN_PROGRESS | Daily and Reader/Ask partial states are truthful; full fixed-fixture rubric/state language remains |
| A-08 | IN_PROGRESS | Clean Alembic upgrade and anchor contracts green; live PostgreSQL restored-snapshot and conditional tests remain |
| A-09 | IN_PROGRESS | Harnesses exist; five-run nonzero Web/API/queue/DB baselines remain |
| A-10 | IN_PROGRESS | Partial retry/metrics exist; bounded recovery, queue restart and correlated fault proof remain |
| A-11 | IN_PROGRESS | Production audit and Trivy green; deterministic maintenance/lockfile review continue at release closure |
| A-12 | IN_PROGRESS | Exact SHA staging deploy/smoke green; rollback/forward and registry cleanup rehearsal remain |
| A-13 | IN_PROGRESS | Current instructions reconciled; clean-clone replay and failure-linked seam evidence remain |
| A-14 | NOT_STARTED | Optional craft work waits for MUST behavior/access/performance gates |
| A-15 | IN_PROGRESS | Mock/provider contract now includes one typed Ask 503/retry/SSE citation; cap/timeout/fallback matrix remains |

## Autonomous Work Queue

1. **M1.3 — next core-loop state slice (P0):** Inventory deterministic fixtures for Keep/annotation and Review/Research/Export; choose the uncovered state with the highest user loss risk, write one failing scenario, implement the smallest recovery.
2. **M1.4 — anchor integrity extension (P0):** Add repeated-quote or refreshed-content restoration/rejection fixture; preserve metadata compatibility and no-wrong-anchor rule.
3. **M2 — accessible responsive interaction (P0):** Start with role-aware contrast tests because known normal-text values are below AA; use the existing editorial system and test reduced-motion/reflow alongside each touch.
4. **M3 — deployment-like data/performance/resilience (P0):** Create disposable PostgreSQL and five-run Web/API/queue/DB baseline paths before tuning.
5. **M5 — release recovery closure (P0):** Rehearse immutable staging rollback/forward and registry cleanup only after prior MUST gates are green.

## Iteration Log

| Timestamp | Decision / result | Evidence / follow-up |
| --- | --- | --- |
| 2026-07-26 | Replaced stale branch/approval ledger with a current autonomous execution ledger. | New goal contract forbids human-response blockers; current `main` is `a23dcaeb`. |
| 2026-07-26 | M1.1 closed one Daily secondary-source continuity slice. | Test first failed, then focused Chromium 1/1, Node 189/189, build, and Chromium 46/46 passed. Record: `output/evidence/m1-daily-partial-failure-2026-07-26.json`. |
| 2026-07-26 | M1.1 merged to `main` as `49b2ecf2` and passed exact-SHA CI/staging. | Run `30175505204` passed test/build/Compose/Trivy, image publication, deployment and route/boundary smoke. |
| 2026-07-26 | M1.2 closed one Reader/Ask transient-failure continuity slice. | Test first failed, then focused Chromium 1/1, Node 189/189, build, and Chromium 47/47 passed. Record: `output/evidence/m1-reader-ask-retry-2026-07-26.json`. |

## Evidence and Recovery Rules

- Record actual command exits, test counts, SHA/base, fixture, and unavailable dependencies. Never convert a skip into a pass.
- Hash all durable evidence after its content is final. Do not put secrets, tokens, production data, or user content in evidence.
- If a focused change fails, stop broadening the diff; repair the first failing layer or revert the slice. After two evidence-backed failed approaches, revert and pursue the next simpler candidate.
- At every milestone boundary: run the relevant full suite, inspect `git diff --check`, update this ledger/learning notes/GOAL decision log, and keep a concrete rollback point.
