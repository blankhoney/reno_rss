# Project Optimization Execution Plan

> Authoritative goal: `GOAL.md`
> Updated: 2026-07-26 (Asia/Taipei)
> Behavior checkpoint: `504c98c7125d6e589872b68c6c8c61311a5350f0` (merged `main`; M2.1 candidate is currently uncommitted)
> Current state: **M2.1 — accessible responsive interaction, A-05/A-06 in progress; core-loop/data/release MUST gates remain open**

## Execution Contract

- `GOAL.md` is authoritative for objective, MUST gates, non-goals, and completion. This file is only the current execution ledger.
- Work on one measurable bottleneck at a time. Begin with the smallest failing test or baseline, retain only complexity that improves a named acceptance row, and commit a reversible slice.
- No human response is required to continue. Missing infrastructure is replaced in priority order by a deterministic fixture, in-memory adapter, Mock, disposable local service, then CI service; missing external proof remains explicit rather than becoming a pass.
- Production, DNS, credentials, irreversible data operations, and real-provider spend remain outside autonomous mutation. Staging and synthetic/local evidence are the delivery boundary.
- Every durable behavior/process change updates `docs/learning-notes.md`; synthetic/redacted evidence is hashed in `output/evidence-sha256.txt`.

## Current Checkpoint

| Field | Current evidence |
| --- | --- |
| Exact candidate | `goal/m1-annotation-integrity` based on merged `main` `504c98c7`; focused M2.1 browser-matrix slice is uncommitted. |
| Milestone / acceptance | M2.1 accessibility/reflow cross-engine minimum; A-05 and A-06 remain `IN_PROGRESS`. |
| Hypothesis | A compact core matrix gives earlier warning for browser-specific caching, overlay, focus and reflow regressions without presenting a subset as full-browser coverage. |
| Initial failure | CI installed only Chromium; the user-switch cache test assumed every safe offline outcome was a synthetic 503, while WebKit safely rejects the offline request. |
| Minimal repair | Add Firefox, WebKit and touch projects filtered to core routes; define cache safety as current-user data, typed offline error, or no response—not a previous-user response. |
| Green validation | Chromium 55/55; Firefox 21/21; WebKit 21/21; iPhone WebKit 20/20; Node 193/193; production build. |
| Durable evidence | `output/evidence/m2-cross-engine-core-2026-07-26.json`, integrity-listed in `output/evidence-sha256.txt`. |
| Rollback | Revert CI browser install, Playwright projects and cache assertion together; no application runtime, schema, API or stored data changes. |
| Next action | Make cross-engine text selection reproducible before calling A-06 complete. |

## Completed Checkpoints

| Checkpoint | Acceptance advanced | Evidence | Remaining boundary |
| --- | --- | --- | --- |
| M0 baseline and evaluation infrastructure | A-01 | Versioned performance/security/Playwright artifacts and verified hash manifest | External browser/PostgreSQL route values remain `NEEDS_BASELINE` |
| Deterministic lint, self-hosted fonts, dependency/security and metrics boundary | A-01, A-04, A-11, A-12, A-15 | Exact-SHA CI/staging proof, pinned tooling, source/license artifacts, internal metrics/public deny, staging rollback-forward and GHCR cleanup dry-run | External-only evidence remains |
| Versioned annotation anchor | A-03, A-04, A-08 | API/OpenAPI/Reader/browser anchor tests | Refresh, repeated-quote, alternate input and session matrix incomplete |
| M1.1 Daily partial failure | A-02, A-07 | One failing test before repair; focused and full Reader validation after repair | One deterministic state slice only; full state/browser/input matrix incomplete |
| M1.2 Reader/Ask partial failure | A-02, A-07, A-15 | One failing test before repair; 503 → retry → SSE citation and full Reader validation | One deterministic Ask failure slice only; provider/recovery/state matrix incomplete |
| M1.3 annotation recovery | A-03, A-04 | Resolver/highlighter test-first failures; shifted-repeat restoration and ambiguity rejection with full Reader validation | Inline-markup, input, retry, and multi-user identity matrix incomplete |
| M1.4 candidate state retry | A-02, A-04, A-10 | One deterministic state-write 503 preserves Reader context; explicit retry reloads server-confirmed candidate state | Broader state matrix, input/browser pairwise coverage, and bounded recovery budget incomplete |
| M1.5 inline-markup annotation recovery | A-03, A-04, A-07 | Cross-markup anchor remains unresolved, and its retained note is available natively | Touch, IME, retry, and multi-user annotation matrix incomplete |
| M2.1 cross-engine accessible core minimum | A-05, A-06 | AA muted-text/reduced-motion assertion and Chromium/Firefox/WebKit/iPhone core paths | Full cross-engine suite, screen-reader and cross-engine selection matrix incomplete |

## Acceptance Ledger

| ID | Status | Current proof / next necessary proof |
| --- | --- | --- |
| A-01 | PASS | Exact revision, evidence manifest, reproducible focused gates |
| A-02 | IN_PROGRESS | Daily Cluster partial-failure/retry/open-return and Reader/Ask 503→retry→citation slices green; complete Daily/Scan → Reader/Ask → Keep → Review/Research/Export state matrix remains |
| A-03 | IN_PROGRESS | Initial anchor plus M1.3 shifted-repeat restoration and ambiguity rejection are green; inline markup, retry, touch-equivalent and keyboard cases remain |
| A-04 | IN_PROGRESS | Annotation ambiguity now keeps private data visible without misbinding; admin/public metrics/session checks exist, and two-user browser/cache matrix remains |
| A-05 | IN_PROGRESS | AA muted-text, reduced-motion and core keyboard/reflow paths now run in the minimum browser matrix; semantic audit and screen-reader evidence remain |
| A-06 | IN_PROGRESS | Chromium 55/55, Firefox/WebKit 21/21 and iPhone WebKit 20/20 core subset green; Scan/Focus/Keep 320/375/390/768/1024/1280/1440 reflow is green in Chromium/Firefox/WebKit; full suite and cross-engine selection/input pairwise matrix remain |
| A-07 | IN_PROGRESS | Daily and Reader/Ask partial states are truthful; full fixed-fixture rubric/state language remains |
| A-08 | IN_PROGRESS | PostgreSQL `project ⇒ saved` invariant and atomic upsert are covered by CI PostgreSQL migration + API contract; latest Alembic downgrade/replay and disposable logical snapshot restore both pass, while recovery-time/write-failure evidence remains |
| A-09 | IN_PROGRESS | Web schema-v2 and CI PostgreSQL fixture baselines have five samples per route/query phase; API/queue memory baselines and a schema-v1/v2 comparator exist, and CI now compares candidates with the latest successful `main` baseline at a 3× threshold; deployment-like write/load evidence remains |
| A-10 | IN_PROGRESS | PostgreSQL CI proves an expired lease is requeued with backoff and completed by a new worker; the worker emits a content-free recovery correlation log, while bounded recovery-time and broader fault proof remain |
| A-11 | IN_PROGRESS | Production audit and Trivy green; deterministic maintenance/lockfile review continue at release closure |
| A-12 | PASS | `sha-2ec6cd2` staging deploy, rollback to published `sha-98d06a4`, and forward replay all passed (`30279882267` → `30280699086` → `30280839157`); repository-scoped GHCR cleanup dry-run `30282030908` validated all manifests without deleting versions |
| A-13 | IN_PROGRESS | Current instructions reconciled; clean-clone replay and failure-linked seam evidence remain |
| A-14 | NOT_STARTED | Optional craft work waits for MUST behavior/access/performance gates |
| A-15 | IN_PROGRESS | Mock/provider contract now includes one typed Ask 503/retry/SSE citation; cap/timeout/fallback matrix remains |

## Autonomous Work Queue

1. **M2.2 — responsive/input extension (P0):** Add a cross-engine reproducible text-selection alternative; preserve the desktop-only shortcut contract on touch projects.
2. **M3 — atomic article state (P0):** Establish PostgreSQL-backed concurrent writes and `project ⇒ saved` storage invariant before tuning performance.
3. **M3.1 — deployment-like performance/resilience (P0):** Measure bounded PostgreSQL lease-recovery time and correlate its logs; retain the existing latest-`main` DB 3× threshold gate.
4. **M4 — release recovery closure (P0):** Complete; retain the non-destructive cleanup dry-run policy and revisit only when an explicitly authorized deletion window is needed.

## Iteration Log

| Timestamp | Decision / result | Evidence / follow-up |
| --- | --- | --- |
| 2026-07-26 | Replaced stale branch/approval ledger with a current autonomous execution ledger. | New goal contract forbids human-response blockers; current `main` is `a23dcaeb`. |
| 2026-07-26 | M1.1 closed one Daily secondary-source continuity slice. | Test first failed, then focused Chromium 1/1, Node 189/189, build, and Chromium 46/46 passed. Record: `output/evidence/m1-daily-partial-failure-2026-07-26.json`. |
| 2026-07-26 | M1.1 merged to `main` as `49b2ecf2` and passed exact-SHA CI/staging. | Run `30175505204` passed test/build/Compose/Trivy, image publication, deployment and route/boundary smoke. |
| 2026-07-26 | M1.2 closed one Reader/Ask transient-failure continuity slice. | Test first failed, then focused Chromium 1/1, Node 189/189, build, and Chromium 47/47 passed. Record: `output/evidence/m1-reader-ask-retry-2026-07-26.json`. |
| 2026-07-26 | M1.3 closed one safe annotation-recovery slice. | Resolver/highlighter tests first failed, then focused Node 9/9, Reader Node 193/193, build, focused Chromium 1/1, and Chromium 48/48 passed. Record: `output/evidence/m1-annotation-anchor-recovery-2026-07-26.json`. |
| 2026-07-26 | M1.4 closed one candidate state-write recovery slice. | First browser run exposed incorrect control naming and a strict alert locator; after those test-only corrections, the deterministic 503 → explicit retry → server-confirmed candidate-state scenario passed. Reader Node 193/193, production build, and Chromium 49/49 passed. Record: `output/evidence/m1-candidate-state-retry-2026-07-26.json`. |
| 2026-07-26 | M2.1 established a minimum cross-engine core matrix and corrected the user-switch offline cache invariant. | Chromium 55/55, Firefox 21/21, WebKit 21/21 and iPhone WebKit 20/20 passed; WebKit's `Load failed` is accepted only as no response, never as cached prior-user data. Record: `output/evidence/m2-cross-engine-core-2026-07-26.json`. |
| 2026-07-26 | M2.2 added 390/1024/1280px to the reader-mode reflow contract. | Chromium, Firefox and WebKit each passed 21 mode×viewport checks. Record: `output/evidence/m2-responsive-widths-2026-07-26.json`. |
| 2026-07-26 | M3.1 established a Web cache-phase baseline that distinguishes cold, HTTP-cache warm and Service Worker-controlled loads. | `evidence/web-performance-baseline-2026-07-26.json`: production build via E2E fixture, two routes × three phases × five samples, all HTTP 200/no browser or network errors; SW phase is asserted controlled. Main CI `30180884268` passed for merged A-08. |
| 2026-07-26 | M3.1 established a disposable PostgreSQL baseline with representative query fixtures. | CI `30181950027` artifact `db-postgres-performance-baseline`: latest/search/ready-job/due-review each have five nonempty samples; p95 0.510/0.496/0.484/0.506 ms. |
| 2026-07-26 | M3.1 added a schema-v1/v2 performance comparator without treating cross-environment measurements as a pass. | `infra/scripts/check-performance-baseline.py` self-compared API/queue and Web `lcpMs`; a synthetic 3.01× API p95 regressed with exit 1. PR #28 CI/staging `30182482954` passed. |
| 2026-07-26 | M3 added latest Alembic downgrade/replay to the PostgreSQL CI path. | `downgrade -1 → upgrade head → current --check-heads` passed in PR #29 CI/staging `30182799323`; snapshot restoration remains separate work. |
| 2026-07-27 | M3.1 added an equivalent-environment candidate DB threshold gate. | PR #31 CI `30183432804` downloaded the latest successful `main` baseline and passed `check-performance-baseline.py --max-regression 3`; CI `30212853939` repeated the comparison. |
| 2026-07-27 | M3 added a disposable PostgreSQL logical snapshot recovery check. | CI `30212853939` artifact `db-postgres-snapshot-restore` restored the fixture into `snapshot_restore_verify` and asserted revision `0011_project_requires_saved`, article, and annotation; it did not access staging/production. |
| 2026-07-27 | M3.1 proved PostgreSQL worker lease recovery across a worker replacement. | PR #34 CI `30213382395` ran `test_postgres_queue_state_machine_sql`: an expired lease was requeued with backoff, claimed by `worker-after-restart`, and marked succeeded. |
| 2026-07-27 | M3.1 added a content-free recovery correlation event. | PR #36 CI `30278849416` verified the worker logs its identity, recovery count and lease threshold only when stale work is reclaimed. |
| 2026-07-27 | M4 completed the staging immutable rollback-forward rehearsal. | Current SHA CI `30279882267` deployed `sha-2ec6cd2`; rollback `30280699086` returned staging to `sha-98d06a4`; manual forward run `30280839157` restored `sha-2ec6cd2` with runtime proof. |
| 2026-07-27 | M4 completed the GHCR cleanup rehearsal without deleting packages. | `30281085629` exposed the missing `reno_rss/` package prefix; after the workflow fix, `30282030908` dry-run enumerated all three packages, applied 30-day/15-tag retention candidates, and passed multi-architecture validation. |

## Evidence and Recovery Rules

- Record actual command exits, test counts, SHA/base, fixture, and unavailable dependencies. Never convert a skip into a pass.
- Hash all durable evidence after its content is final. Do not put secrets, tokens, production data, or user content in evidence.
- If a focused change fails, stop broadening the diff; repair the first failing layer or revert the slice. After two evidence-backed failed approaches, revert and pursue the next simpler candidate.
- At every milestone boundary: run the relevant full suite, inspect `git diff --check`, update this ledger/learning notes/GOAL decision log, and keep a concrete rollback point.
