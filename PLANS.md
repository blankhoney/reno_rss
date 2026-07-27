# Project Optimization Execution Plan

> Authoritative goal: `GOAL.md`
> Updated: 2026-07-28 (Asia/Taipei)
> Behavior checkpoint: `39422aee25f21adaaa2682e8ada15badc82df57c` (merged `main`; PR #40)
> Current state: **M3.1 PostgreSQL lease-recovery budget established; A-10 broader fault matrix and core-loop MUST gates remain open**

## Execution Contract

- `GOAL.md` is authoritative for objective, MUST gates, non-goals, and completion. This file is only the current execution ledger.
- Work on one measurable bottleneck at a time. Begin with the smallest failing test or baseline, retain only complexity that improves a named acceptance row, and commit a reversible slice.
- No human response is required to continue. Missing infrastructure is replaced in priority order by a deterministic fixture, in-memory adapter, Mock, disposable local service, then CI service; missing external proof remains explicit rather than becoming a pass.
- Production, DNS, credentials, irreversible data operations, and real-provider spend remain outside autonomous mutation. Staging and synthetic/local evidence are the delivery boundary.
- Every durable behavior/process change updates `docs/learning-notes.md`; synthetic/redacted evidence is hashed in `output/evidence-sha256.txt`.

## Current Checkpoint

| Field | Current evidence |
| --- | --- |
| Exact candidate | `goal/m1-annotation-input-continuity @ a6df7919`（base `origin/main @ 97cd28e1`）；PR #44 contains 6 M1.7 slices. |
| Milestone / acceptance | M1.7 annotation/input continuity substantially complete; A-03/A-04 advanced with IME, retry, isolation, two-user proofs. |
| Hypothesis | M1.7 的五个子 slice 分别证明：IME 组合安全、503 显式重试、内容域锚点、会话切换隔离、双上下文隔离。 |
| Initial failure | 各 slice 均有 test-first failure：IME Node test、503 mark assertion（prefix 含 UI 文本）、session-switch/two-user 无 per-user 存储。 |
| Minimal repair | `isSelectionDismissEvent` + `anchorContentRef` + inline retry UI + `onPointerDown` + per-user `userAnnotations` Map。 |
| Green validation | Reader Node 194/194；production build；fresh-server Chromium 70 passed（含全部新增场景）。 |
| Durable evidence | `output/evidence/m1-ime-selection-continuity-2026-07-27.json`、`m1-annotation-save-retry-2026-07-27.json`、`m1-session-switch-isolation-2026-07-27.json`、`m1-two-user-isolation-2026-07-27.json`；全部列入 `output/evidence-sha256.txt`。 |
| Rollback | Revert PR #44 的 6 个 commit；无 schema、API 契约或生产运行时变更。 |
| Next action | 推进 A-02 核心状态矩阵：优先补齐 Keep/Scan/Focus 模块的 loading/empty/error/retry/server-confirmed 路径。 |

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
| M3.1 bounded queue lease recovery | A-10 | Competing-job regression plus 5 PostgreSQL samples through replacement-worker success; full CI/images/staging green | Database outage, lock contention, timeout and retry-exhaustion matrix remains |
| M1.7 IME selection continuity | A-03, A-02 | Composition-aware dismiss test-first failure; composing Escape preserves the anchor through save in Chromium | Touch save, annotation 503 retry, session-switch and two-user annotation matrix incomplete |
| M1.7 annotation save 503 retry | A-03, A-02, A-06 | 503 → explicit retry → success with anchor-backed highlight; anchor built from content text, not article element; onPointerDown prevents touch selection collapse; anchor round-trip e2e added | Touch selection automation, session-switch and two-user annotation matrix incomplete |
| M1.7 session-switch annotation isolation | A-03, A-04 | Per-user annotation storage in e2e server; user B does not see user A's created annotation after login switch; Chromium 69 passed | Two-user concurrent browser matrix incomplete |
| M1.7 two-user concurrent isolation | A-03, A-04 | Two browser contexts: ada creates annotation 60, babbage context sees fixture 41 only; no cross-context leakage; Chromium 70 passed | Touch selection automation and full cross-engine annotation matrix remain |

## Acceptance Ledger

| ID | Status | Current proof / next necessary proof |
| --- | --- | --- |
| A-01 | PASS | Exact revision, evidence manifest, reproducible focused gates |
| A-02 | IN_PROGRESS | Daily, Reader/Ask, Keep/starred (empty/populated/error/retry), Review (error/retry), Export (download), and Research (failed retry) slices green; Scan/Focus visual mode paths and cross-engine coverage remain |
| A-03 | IN_PROGRESS | Initial anchor plus M1.3 shifted-repeat, ambiguity rejection, M1.5 inline-markup, M1.7 IME dismiss, save 503→retry with content-scoped anchor, session-switch isolation, and two-user concurrent isolation are green; touch selection automation and full cross-engine annotation matrix remain |
| A-04 | IN_PROGRESS | Annotation ambiguity keeps private data visible; admin/public metrics/session checks exist; M1.7 session-switch and two-user concurrent contexts prove no cross-user annotation leakage; full two-user cache/Service-Worker matrix remains |
| A-05 | IN_PROGRESS | AA muted-text, reduced-motion and core keyboard/reflow paths now run in the minimum browser matrix; semantic audit and screen-reader evidence remain |
| A-06 | IN_PROGRESS | Chromium 55/55, Firefox/WebKit 21/21 and iPhone WebKit 20/20 core subset green; Scan/Focus/Keep 320/375/390/768/1024/1280/1440 reflow is green in Chromium/Firefox/WebKit; full suite and cross-engine selection/input pairwise matrix remain |
| A-07 | IN_PROGRESS | Daily and Reader/Ask partial states are truthful; full fixed-fixture rubric/state language remains |
| A-08 | IN_PROGRESS | PostgreSQL `project ⇒ saved` invariant and atomic upsert are covered by CI PostgreSQL migration + API contract; latest Alembic downgrade/replay and disposable logical snapshot restore both pass, while recovery-time/write-failure evidence remains |
| A-09 | IN_PROGRESS | Web schema-v2 and CI PostgreSQL fixture baselines have five samples per route/query phase; API/queue memory baselines and a schema-v1/v2 comparator exist, and CI now compares candidates with the latest successful `main` baseline at a 3× threshold; deployment-like write/load evidence remains |
| A-10 | IN_PROGRESS | PostgreSQL CI proves an expired lease is requeued and completed by a replacement worker; a competing ready job remains untouched; 5 samples have median 5.614 ms/p95 7.956 ms; content-free recovery logs exist, while database outage/lock/timeout/retry-exhaustion proof remains |
| A-11 | IN_PROGRESS | Production audit and Trivy green; deterministic maintenance/lockfile review continue at release closure |
| A-12 | PASS | `sha-2ec6cd2` staging deploy, rollback to published `sha-98d06a4`, and forward replay all passed (`30279882267` → `30280699086` → `30280839157`); repository-scoped GHCR cleanup dry-run `30282030908` validated all manifests without deleting versions |
| A-13 | IN_PROGRESS | Current instructions reconciled; clean-clone replay and failure-linked seam evidence remain |
| A-14 | NOT_STARTED | Optional craft work waits for MUST behavior/access/performance gates |
| A-15 | IN_PROGRESS | Mock/provider contract now includes one typed Ask 503/retry/SSE citation; cap/timeout/fallback matrix remains |

## Autonomous Work Queue

1. **M1.6 — core visible-state matrix (P0):** Version Daily/Scan → Reader/Ask → Keep states and close loading/empty/error/retry/server-confirmed gaps with deterministic fixtures.
2. **M1.7 — annotation/input continuity (P0):** Close touch, IME, retry, session and two-user anchor cases without unsafe rebinding.
3. **M1.8 — identity/provider boundaries (P0):** Complete two-user cache/API isolation and provider cap/timeout/fallback/idempotency matrix.
4. **M2.2 — accessibility/input extension (P0):** Complete semantic/focus/reduced-motion evidence, then retry a reproducible cross-engine selection alternative.
5. **M3.2 — broader fault matrix (P0):** Add database outage, lock contention, timeout and retry-exhaustion recovery evidence while retaining the current five-sample budget.
6. **M4 — release recovery closure (P0):** Complete; retain the non-destructive cleanup dry-run policy.

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
| 2026-07-28 | M3.1 reproduced queue-baseline contention before repair. | Initial artifact `30282641983` reported `RuntimeError`; test-only commit `801a9b6b` and CI `30284173132` added a priority-1 ready competitor and failed exactly because the baseline consumed other work. |
| 2026-07-28 | M3.1 established a deterministic bounded PostgreSQL lease-recovery baseline. | PR #40 / CI `30284291417` kept the competitor queued, measured five replacement-worker recoveries (median 5.614 ms, p95 7.956 ms), uploaded the artifact, and passed full quality/images/staging. |
| 2026-07-27 | M1.7 closed the IME-composition selection continuity slice. | Node test and stash-reverted Chromium e2e first failed; after the composition-aware dismiss fix, focused Node 6/6, Reader Node 194/194, production build and fresh-server Chromium 65 passed (1 pre-existing flaky green on retry/isolation). Record: `output/evidence/m1-ime-selection-continuity-2026-07-27.json`. |
| 2026-07-27 | M1.7 closed the annotation save 503→retry continuity slice. | E2e test first failed at mark assertion (anchor prefix contained UI text, start 158 not 0); after `anchorContentRef` fix and inline retry UI, Reader Node 194/194, production build and fresh-server Chromium 67 passed. Record: `output/evidence/m1-annotation-save-retry-2026-07-27.json`. |
| 2026-07-27 | M1.7 closed the session-switch annotation isolation slice. | Per-user annotation storage in e2e server; user A creates annotation, switches to user B via login, B sees fixture but not A's annotation. Chromium 69 passed. Record: `output/evidence/m1-session-switch-isolation-2026-07-27.json`. |
| 2026-07-27 | M1.7 closed the two-user concurrent annotation isolation slice. | Two browser contexts: ada creates annotation 60, babbage context sees fixture 41 only; no cross-context leakage. Chromium 70 passed. Record: `output/evidence/m1-two-user-isolation-2026-07-27.json`. |
| 2026-07-27 | A-02 added Keep/starred module state matrix. | Empty state (no saved articles), populated list (server saved:true via page.route), and article list 503→retry recovery with fail-once toggle. Chromium 73 passed. Record: `output/evidence/a02-keep-state-matrix-2026-07-27.json`. |
| 2026-07-27 | A-02 added Review error/retry and Export download coverage. | Review fail-once 503→retry→queue loads; Export fixture endpoint with markdown download and success message. Chromium 75 passed. Record: `output/evidence/a02-review-export-matrix-2026-07-27.json`. |

## Evidence and Recovery Rules

- Record actual command exits, test counts, SHA/base, fixture, and unavailable dependencies. Never convert a skip into a pass.
- Hash all durable evidence after its content is final. Do not put secrets, tokens, production data, or user content in evidence.
- If a focused change fails, stop broadening the diff; repair the first failing layer or revert the slice. After two evidence-backed failed approaches, revert and pursue the next simpler candidate.
- At every milestone boundary: run the relevant full suite, inspect `git diff --check`, update this ledger/learning notes/GOAL decision log, and keep a concrete rollback point.
