# Project Optimization Execution Plan

> Goal source: `GOAL.md`
> Started: 2026-07-26 (Asia/Taipei)
> Execution branch: `feat/frontend-excellence`
> Starting committed revision: `609724d7f39182270bdeaf0c79a4b928b01054b9`
> Status: **M1 in progress — all three bounded implementation slices approved**

## Execution Contract

- `GOAL.md` defines the objective, MUST criteria, boundaries, and stop conditions. This file only records execution order and current evidence.
- Work on one highest-value bottleneck at a time. Each slice names its acceptance IDs, before evidence, target, verification, and rollback point.
- Preserve the intent and history of the five business files that were user-owned at startup and delegated on 2026-07-26:
  - `apps/api/app/api/routes/articles.py`
  - `apps/api/app/domain/annotations_meta.py`
  - `apps/reader-web/src/components/FocusedArticleReader.tsx`
  - `apps/reader-web/src/lib/api/articles.ts`
  - `apps/reader-web/src/lib/articles/selection.ts`
- Use an isolated worktree for the dependency candidate before changing the main worktree.
- Do not commit, push, open/merge a PR, deploy, mutate production, spend real LLM budget, or perform destructive registry/data work without the authority required by the active run.
- Record current evidence in `docs/goal-evidence.md`; historical ledgers remain historical.

## Completed Milestone: M0 — Baseline and Evaluation Infrastructure

### M0 success criteria

- A-01 has an exact-SHA evidence ledger with current-worktree versus clean-HEAD status explicitly separated.
- Principal browser fixtures can render representative success states for Daily Intelligence, workbench, reader, Review, Search, Research, Export, and Admin.
- Unexpected browser `console.error` and `pageerror` events fail the relevant core-loop smoke tests unless explicitly allowlisted with a reason.
- Repeatable frontend, API, DB, and queue baseline procedures exist. Unavailable environments remain explicit `NEEDS_BASELINE`, never inferred.
- The M0 full gate is run and logged without overwriting user-owned dirty files.

### Completed slices

| Slice | Acceptance | Result | Verification |
| --- | --- | --- | --- |
| M0.1 planning and evidence ledger | A-01, supports A-02/A-11/A-15 | Exact-SHA plan and evidence ownership established without touching user-owned business files | Structural review; `git diff --check` |
| M0.2 representative fixture and unexpected-console gate | A-01, A-07 | Default E2E state now renders representative Daily, workbench, reader, Review, Search, Research, Export, and Admin content; explicit `fixture=daily-error` preserves the failure scenario; success flow rejects `console.error`/`pageerror` | Test failed before fixtures; final isolated run: 43 Chromium passed; representative screenshot reviewed |
| M0.3 repeatable performance procedures | A-11, supports A-01/A-14 | Web/API/queue/DB procedures emit versioned redacted JSON. API and in-memory queue were measured twice; Web project routes and PostgreSQL remain explicit `NEEDS_BASELINE`. | Script syntax; duplicate run/schema assertions; DB unavailable exit 2; Reader/API/Worker full unit suites green |
| M0.4 environment inventory and checkpoint | A-01, supports A-02/A-08/A-10/A-12 | Available engines/services/transports are explicit; every output artifact is SHA-256 manifested; unavailable gates are not treated as pass | Read-only probes; `shasum -a 256 -c output/evidence-sha256.txt`; `git diff --check`; evidence audit |

## Current Milestone: M1 — Release Gate and Security Boundary

### Completed M1 slices

| Slice | Acceptance | Result | Verification |
| --- | --- | --- | --- |
| M1.1 deterministic Python lint toolchain | A-02, supports A-12/A-15 | Both Python dev extras pin Ruff 0.15.22; no broad source auto-fix | 0.14/0.15 clean vs 0.16 API 200/Worker 54; standard offline isolated Ruff commands pass |
| M1.2 deterministic frontend font delivery | A-02, supports A-11/A-12/A-14/A-15 | Newsreader Latin variable normal/italic files and OFL are self-hosted through `next/font/local`; CJK retains the existing system fallback chain; build no longer imports Google Fonts | Two clean native builds produce identical 1,816 KiB static/39,084 KiB standalone footprints and two WOFF2 assets; 185 Node and 43 Chromium pass; representative home/reader screenshots reviewed |
| M1.3a frontend production dependency remediation | A-03, supports A-02/A-12 | Next is fixed at 16.2.11 and minimum PostCSS 8.5.18/Sharp 0.35.0 overrides remove all production audit findings | Isolated `npm ci`; production audit 0; full audit only one development low; 185 Node, production build, 43 Chromium, and `git diff --check` pass |
| M1.3b internal-only metrics boundary | A-05, supports A-12/A-15 | Both public AI Reader hosts deny exact `/api/metrics` with 404; the worker smoke probe uses the environment API alias on the shared app network | Static route-order contract, shell syntax, API metrics 3/3, staging/prod/edge Compose render pass; Docker/Caddy live proof remains |
| M1.3c annotation-anchor release repair | A-04, supports A-06/A-10/A-15 | The delegated five-file slice now persists a typed versioned text-quote anchor, preserves it across editor focus, and synchronizes OpenAPI/generated TS | API 219 and Ruff; Reader 189, build, Chromium 45; two anchor browser scenarios; OpenAPI and generated client drift-free |

### Active slice M1.3 — Release/security decisions and current-truth documentation

| Field | Value |
| --- | --- |
| Acceptance | A-03, A-05, A-15; supports A-02/A-12 |
| Before evidence | Three high production dependency findings require D-02; public staging metrics require an approved scrape boundary; active docs contain verified retired scorer/auth/frontend claims |
| Target | Produce decision-ready, non-mutating dependency and metrics boundary records while correcting only active documentation statements that can be proven from current code/config |
| Verification | Advisory/package graph inventory without dependency mutation; documentation truth matrix and documented-command checks; `rg` for retired active claims; `git diff --check` |
| Rollback | Documentation/evidence-only changes remain separable; no lockfile, edge, secret, live service, or user-owned anchor mutation before the required decisions |
| Status | IN_PROGRESS — all three approved mutations are implemented and pushed; exact-candidate CI and live D-04 proof remain |

## Later Milestones

| Milestone | Primary acceptance | Entry gate | Highest known blocker |
| --- | --- | --- | --- |
| M2 — Core-loop truth and knowledge integrity | A-06–A-07, A-10 | M1 complete | FEX-19–22 and remaining FEX-17 state matrix |
| M3 — Accessible, responsive visual contract | A-08–A-09, A-13 | M2 complete | D-01 action-accent decision |
| M4 — Performance, resilience, maintainability | A-11–A-15 | M3 complete and budgets approved | Nonzero DB/web/API baselines; GHCR cleanup ownership |
| M5 — Release-candidate and staging proof | All MUST | M0–M4 complete | Same-repo CI/VPS staging authority and exact-SHA deploy proof |

## Acceptance Status

Status values are `NOT_STARTED`, `IN_PROGRESS`, `PASS`, or `BLOCKED`. A prior run does not yield `PASS` for the current candidate.

| ID | Status | Current evidence / next proof |
| --- | --- | --- |
| A-01 | PASS | Exact-SHA ledger, environment limits, current acceptance links, screenshots/reports, and verified SHA-256 manifest are present |
| A-02 | IN_PROGRESS | Deterministic Ruff and local-font builds are green; dirty candidate, schema drift, conditional environments, and current CI remain red/missing |
| A-03 | IN_PROGRESS | D-02 candidate is applied after isolated production audit 0, 185 Node, build, and 43 Chromium; exact final candidate CI/Trivy remains |
| A-04 | PASS | Delegated anchor slice is committed as `01011e02`; API 219/Ruff, Reader 189/build/45 Chromium, and OpenAPI/generated-schema drift gates pass |
| A-05 | IN_PROGRESS | Exact public 404 and internal worker-to-alias smoke contract are implemented; local static/API/Compose gates pass, but live post-deploy proof remains |
| A-06 | NOT_STARTED | FEX-19–22 pending |
| A-07 | IN_PROGRESS | Representative principal success fixtures and unexpected-console gate pass; complete state matrix remains |
| A-08 | IN_PROGRESS | Chromium partial proof; project-compatible Firefox/WebKit binaries are not installed |
| A-09 | NOT_STARTED | Contrast candidates below AA; D-01 unresolved |
| A-10 | IN_PROGRESS | PG procedure exists; local PG tool/URL unavailable; four tests still skipped |
| A-11 | IN_PROGRESS | Self-hosted fonts reduce native static output from 8,424 to 1,816 KiB; repeatable Web harness exists; project-route/live-DB baselines remain missing |
| A-12 | NOT_STARTED | Current branch CI remains unverified; local `gh` and connector transport unavailable; GHCR cleanup previously failed |
| A-13 | NOT_STARTED | Baseline screenshots exist; rubric not scored with representative fixtures |
| A-14 | IN_PROGRESS | Font asset count drops 107→2 with visual/E2E proof; runtime motion and user-timing budgets remain missing |
| A-15 | IN_PROGRESS | Tracked bilingual demo/CI docs and ignored historical labels are corrected; final exact-candidate command/link/diff review remains |

## Decisions and Authorities

| Decision | State | Work allowed before decision |
| --- | --- | --- |
| D-01 terracotta vs indigo | Pending maintainer | M0–M2 and non-palette accessibility diagnosis |
| D-02 dependency remediation | Implemented and pushed (`c61cd6a6`) | Retain overrides until Next's declared ranges catch up; exact-candidate CI still gates M1 |
| D-03 production intent | Pending maintainer | Staging/local work and read-only public probes only |
| D-04 metrics trust boundary | Implemented and pushed (`cafc4cc1`) | Exact public 404 plus internal environment-alias scrape is locally verified; live VPS proof remains |
| User-owned anchor slice | Completed and pushed (`01011e02`) | Typed contract, persistence, API/client schema, build, and browser editor-focus paths are green |

## Iteration Log

| Timestamp | Completed | Validation | Architecture change | Current risk | Next action |
| --- | --- | --- | --- | --- | --- |
| 2026-07-26 | Goal activated; all AGENTS read; Git and dirty ownership re-checked; M0 plan started | HEAD/origin both `609724d7`; `PLANS.md` was absent | None | Dirty anchor slice blocks current build; evidence is fragmented | Create exact-SHA evidence ledger, then make browser fixtures trustworthy |
| 2026-07-26 | M0.1 exact-SHA ledger and M0.2 representative fixture/console gate | New test failed before fixture support; isolated final E2E 43/43; screenshot reviewed; `git diff --check` | Test/evaluation infrastructure only; runtime product code unchanged | Native Next build can fail when Google Fonts is unreachable; current dirty slice still blocks current-worktree build | Finish M0.3 with API/DB/queue procedures and keep project Web timing `NEEDS_BASELINE` until the target is trustworthy |
| 2026-07-26 | First Web performance harness slice | `node --check`; two fixed local runs; schema/status/error assertions true | New read-only measurement CLI; no product runtime change | Chromium cannot currently reach external HTTPS; local build has network-coupled fonts | Add nonzero API/DB/queue baseline procedures, then inventory environment gates |
| 2026-07-26 | M0.3 API/queue/DB procedures and M0.4 initial environment inventory | API and queue repeated twice; DB emits `NEEDS_BASELINE`; Reader 185, API 217, Worker 121/4 skips; read-only environment probes complete | Measurement scripts only; no application runtime behavior changed | No project Firefox/WebKit, Docker daemon, PG URL/tool, or working GitHub transport | Finish M0 checkpoint evidence audit and identify the first M1 issue not requiring a pending product decision |
| 2026-07-26 | M0 checkpoint complete; A-01 passed | Artifact SHA-256 manifest verifies; `git diff --check` passes; all unavailable gates linked to explicit evidence | M0 adds evaluation infrastructure only; application runtime remains unchanged | A-11 still needs real Web/PostgreSQL values; M1 still has D-02/metrics/anchor decisions | Start M1.1 by resolving the time-dependent Ruff gate without touching user-owned files |
| 2026-07-26 | M1.1 pinned Ruff 0.15.22 | 0.14.11/0.15.22 clean; 0.16.0 API 200/Worker 54; exact offline standard commands green | Toolchain constraint only; no Python source auto-fix | Frontend build still depends on live Google Fonts; dirty anchor still blocks current-worktree build | Make font delivery deterministic without changing the design direction or adding a dependency |
| 2026-07-26 | M1.2 self-hosted Newsreader Latin variable fonts with adjacent OFL | Two native builds green and identical; 185 Node; 43 Chromium; source/emitted external-font scan empty; 1440 px home/reader screenshots reviewed; `git diff --check` | Build-time font network dependency removed; CJK continues through the existing system serif fallback; no package added | Dirty anchor, D-02 dependency findings, public metrics, CI/live PG/cross-engine remain | Prepare D-02/metrics decisions and repair only evidence-backed active documentation drift |
| 2026-07-26 | M1.3 decision evidence, doc truth, and local secret mode | Audit chain/dry-run and metrics network inventory recorded without mutation; six public-doc link sets and stale-claim scan pass; `.env` 0644→0600 without content read | No dependency/edge behavior change; current public contracts now match staging demo/CI; local secret metadata tightened | D-02 and D-04 require maintainer approval; live VPS/CI still unavailable | Request the two bounded approvals; if granted, validate each candidate in isolation before changing the main worktree |
| 2026-07-26 | M1.3 explicit Trivy secret gate | Official-checksum Trivy 0.69.3 secret-only scan on the clean goal-owned candidate snapshot exits 0 with 0 findings; YAML assertion confirms pinned version/scanners | CI supply-chain contract only: filesystem scan now explicitly covers vulnerabilities and secrets; no runtime behavior/dependency change | Exact-candidate CI still missing; vulnerability half remains red under D-02 | Audit whether any other M1 work is possible without the three pending authorities |
| 2026-07-26 | M1 blocked after the third consecutive unanswered authority turn | Evidence manifest and `git diff --check` remain green; no new authorization appeared; user-owned files remain preserved | No implementation change; status now reflects the real execution boundary | A-03/D-02, A-04/anchor ownership, and A-05/D-04 prevent M1 closure and therefore M2 entry | Maintainer replies with the approved subset of `1` dependency remediation, `2` metrics boundary, and `3` anchor completion |
| 2026-07-26 | Maintainer approved all three bounded slices (`1`, `2`, `3`) | Goal status resumed; current worktree and governing `AGENTS.md` re-checked before mutation | D-02 package/lockfile work must prove compatibility in isolation; D-04 uses the existing app network as the internal trust boundary; anchor ownership transfers for completion only | Live metrics proof and exact-candidate CI/deploy still require their normal later gates | Validate and land D-02, then D-04, then the annotation-anchor contract |
| 2026-07-26 | D-02 minimum compatible dependency candidate applied | Isolated `npm ci`; production audit 0; full audit 1 development low; 185 Node; Next build; 43 Chromium; lockfile family review; `git diff --check` | Next is exact-pinned at 16.2.11; PostCSS 8.5.18 and Sharp 0.35.0 are constrained with npm overrides because Next still declares affected ranges | Exact final-candidate CI/Trivy remains; overrides must be re-evaluated when Next's declared ranges catch up | Implement D-04 without changing the API's internal metrics contract |
| 2026-07-26 | D-04 exact public deny and internal alias scrape implemented | Static boundary checker, smoke syntax, API metrics 3/3, and all three Compose renders pass; local Caddy binary and Docker daemon unavailable | Caddy denies only the public metrics path; internal FastAPI contract remains 200 over the existing app network | Live public 404/internal 200 must be proven after deployment | Complete the delegated annotation-anchor slice |
| 2026-07-26 | Delegated annotation-anchor slice completed | Test-first failures reproduced; API 219/Ruff, Reader 189/build, 45 Chromium, and OpenAPI/generated TypeScript drift checks pass | Versioned text-quote anchors use existing metadata storage with no migration; immutable anchor is captured before editor focus can detach the DOM Range | Anchor-aware restoration after content changes remains M2/A-06 scope; standalone `tsc` has three disclosed pre-existing test-only errors | Run exact-candidate release gates and inspect same-repository CI |
