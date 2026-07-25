# Project Optimization Goal

## 0. Document Contract

This file is the authoritative, self-contained contract for the long-running evolution of AI Reader.

- `AGENTS.md` defines durable engineering rules.
- `GOAL.md` defines the single product outcome, boundaries, priorities, evidence, acceptance gates, autonomous decision rules, and finish condition.
- `PLANS.md` is a replaceable execution ledger. If it conflicts with this file, this file wins and the next run repairs `PLANS.md`.
- No run may weaken a MUST gate, expand into an unrelated product, invent evidence, expose a secret, or silently reinterpret a failure as success.
- A run may correct stale baseline facts, tighten a target after repeatable measurement, add a newly evidenced risk, split a milestone, or change an implementation path while preserving the primary objective.
- Missing accounts, credentials, external services, browsers, or infrastructure never become a human-response blocker. The run uses a local service, temporary database, adapter, deterministic fixture, Mock, or safe degradation; records exactly which external proof remains absent; and continues every independent item.
- The contract has no permanent `BLOCKED` state. Unsafe or unavailable actions are contained and replaced, retried later, or excluded by an already-defined non-goal without stopping unrelated progress.

## 1. Primary Objective

Evolve AI Reader into a trustworthy daily research workspace for a self-hosting researcher or small team: a user can move from Daily Intelligence or Scan, through focused reading and grounded AI assistance, into private highlights, notes, review, research, and export without losing context, crossing identity boundaries, seeing false states, or being trapped by viewport, keyboard, failure, or deployment drift. The repository reaches a deliverable state when one exact revision passes every MUST gate in §7, its user-visible core loop is proven across the required state/input/browser matrix, its data and staging release are reproducible and rollback-ready, and every remaining limitation is both disclosed and outside the core outcome.

## 2. User-Visible End State

- A public demo visitor immediately understands the product and can enter the shared functional demo; a private deployment can retain the same workflow without inheriting shared-demo assumptions.
- Daily Intelligence and Scan present truthful loading, success, partial-failure, empty, stale, and retry states. Successful content remains usable when a secondary request fails.
- Opening an article preserves list position and navigation context. Focus mode makes the article primary without hiding essential actions.
- Ask/Agent answers are explicitly grounded in the current article and available project data. Mock-provider tests prove behavior without claiming real-provider quality or spending external credits.
- A selection made by mouse, touch-equivalent input, or keyboard can become a highlight or note. Editor focus does not lose it; repeated text, inline markup, refreshed content, retries, and session changes cannot silently attach knowledge to the wrong passage or user.
- Search, Research, Review, Export, and Admin expose complete state vocabulary and role boundaries. Non-admin users cannot enter Admin data.
- The six anchor widths from 320 to 1440 px have no horizontal overflow, fixed-layer collision, unreachable control, or inappropriate desktop-only hint. Keyboard, reduced-motion, light/dark, Chromium, Firefox, and WebKit preserve the core outcome.
- Required text and controls meet WCAG 2.2 AA semantics and contrast. Motion is purposeful, bounded, compositor-safe where practical, and absent when reduced motion is requested.
- The warm-paper, editorial, terracotta system remains the product identity because it is the implemented and evidenced direction. Improvement comes from hierarchy, evidence, reading rhythm, and state craft—not generic dashboard decoration.
- Failures are explicit, recoverable, and observable. Session-private state is not retained across logout or user change.
- An exact Git revision produces immutable images, upgrades a clean/restored PostgreSQL database safely, deploys to staging, passes smoke and browser probes, and retains a tested rollback point. Production remains fail-closed and outside this goal’s mutation boundary.

## 3. Verified Baseline

Snapshot: 2026-07-26, repository `blankhoney/reno_rss`.

| Dimension | Verified current state | Evidence | Confidence | Missing evidence |
| --- | --- | --- | --- | --- |
| Git and delivery | PR #15 was merged with merge commit `969a077a`; its parent `2fc54886` preserves the focused branch history. Independent PR run `30173143405` and main push run `30173396803` both passed all three jobs. Main deployed exact tag `sha-969a077`; internal metrics scrape passed; health/articles returned 200, non-admin Admin returned 403, and public metrics returned 404. | Git history; PR #15; GitHub Actions runs `30173143405` and `30173396803` | High | Rollback/forward rehearsal and GHCR cleanup |
| Product topology | Next.js Reader Web, FastAPI API, asynchronous Worker, PostgreSQL, Miniflux, Caddy, and Authelia form the current product. Staging is a public shared-user functional demo; Admin remains role-protected. | Compose/Caddy; README/technical docs; API dependencies | High | Private-deployment end-to-end fixture |
| Reader correctness | 189 Node tests, production build, and 45 Chromium browser scenarios pass on the merged candidate. Representative fixtures cover eight primary surfaces and fail on unexpected console/page errors. | PR/main CI; `apps/reader-web`; Playwright report | High | Firefox/WebKit; full A-02/A-06 state and input matrix |
| API correctness | 219 tests and Ruff 0.15.22 pass. Pydantic, OpenAPI, and generated TypeScript agree on the versioned annotation-anchor contract. | CI; `output/anchor/annotation-anchor-contract-2026-07-26.json` | High | Restored-snapshot PostgreSQL behavior |
| Worker correctness | 121 tests pass; 4 PostgreSQL-conditional tests skip in the local baseline. Ruff 0.15.22 passes. | Local baseline; CI | High | Execute all four conditional tests on PostgreSQL |
| Database/migrations | CI performs a clean Alembic upgrade. Local DB benchmark records zero measured queries and is correctly marked unavailable. | CI; `output/performance/db-needs-baseline-2026-07-26.json` | High | Restored snapshot, upgrade/rollback rehearsal, query plans and nonzero timings |
| Annotation integrity | Typed version-1 text-quote anchors persist exact/prefix/suffix/start/end and survive note-editor focus. Anchor-only persistence and invalid ranges are tested. | Commit `01011e02`; API/Reader/browser tests | High | Repeated quote, inline markup, refreshed content, remaining input/retry/session cases |
| Auth/privacy | Session/cache/Admin tests exist. Staging smoke returns Admin 403 for a non-admin. The ignored local `.env` contents were not read and its mode is 0600. | Tests; mode-only evidence; staging smoke | High locally/staging | VPS filename/mode-only inventory; full user A→B browser matrix |
| Metrics/observability | Public exact `/api/metrics` returns 404 while Worker can scrape the environment API alias internally. Request, queue, scheduler, failure, and LLM-account metric families exist. | Run `30173143405`; Caddy/smoke contracts | High for staging | Alert semantics and request/job log correlation; tracing is not yet justified |
| Dependency security | Next 16.2.11 plus PostCSS 8.5.18 and Sharp 0.35.0 overrides produce 0 production npm findings; full audit has one development-only low. Pinned Trivy vulnerability/secret scan passes. | `output/security/frontend-dependency-remediation-2026-07-26.json`; CI | High as of snapshot | Re-evaluate overrides after upstream range changes; action-runtime deprecation maintenance |
| Frontend assets | Self-hosting two licensed Newsreader WOFF2 files reduced repeatable native `.next/static` output from 8,424 to 1,816 KiB; `.next/standalone` is 39,084 KiB. | `output/performance/frontend-font-build-2026-07-26.json` | High for filesystem size | Route transfer, Web Vitals, CPU, long tasks, low-end device/network: `NEEDS_BASELINE` |
| Accessibility | Named landmarks/controls, keyboard tests, focus handling, and global reduced-motion behavior exist. Light `muted/bg`, `muted/panel`, and `accent/bg` candidates measure 3.40:1, 3.71:1, and 4.23:1, below 4.5:1 for required normal text. | Semantic snapshots; tests; token calculation | High for known gaps | Automated audit, role-aware contrast map, screen-reader, 200% zoom/reflow, cross-engine |
| Responsive/motion | Chromium covers selected breakpoints. Mobile still risks desktop hint density. Width animation and blur/backdrop effects have no runtime performance evidence. | Screenshots; CSS/source scan | Medium-high | Six-width pairwise matrix and normal/reduced traces |
| Visual/product identity | The implemented warm editorial system is coherent enough to recognize, but hierarchy, density, whitespace, and state polish vary. Old indigo prose is historical, not an active design direction. | Current source and baseline screenshots | High | Fixed-fixture rubric score across every core surface |
| Performance | Repeatable in-memory API and queue harnesses exist; project-route Web and real DB values are missing. No user-task completion timing exists. | `output/performance/` | High | Nonzero repeatable Web/API/queue/DB baselines and derived budgets |
| CI/CD/rollback | Main run `30173396803` builds and pushes three revision-labelled images and deploys exact SHA `969a077a` to staging. GHCR cleanup run `29721686230` failed package lookup/ownership. Rollback procedure exists but current-candidate rehearsal is unproven. | Workflows/logs | High | Rollback/forward rehearsal and cleanup dry-run/success |
| Stability | Representative success and one explicit Daily failure fixture are truthful and console-gated; the complete loading/empty/partial-error/retry continuity matrix is not closed. | E2E fixtures/tests | High | A-02 full state matrix and recovery timing |
| Documentation/maintainability | Active bilingual docs match the public demo and current CI. Retired local docs are labelled historical. `globals.css`, `FocusedArticleReader.tsx`, `ProductModules.tsx`, adapters, and the main E2E file remain large hotspots; size alone is not evidence to split them. | Source/doc review | High | Newcomer command replay; failure-linked seam evidence |
| Production | Public production API probes returned 502. This goal does not mutate or promote production; it requires fail-closed behavior and completes against staging. | Read-only status probes | High for observed state | Root cause is operational context, not required for staging completion |
| External AI | Staging uses MiniMax. Runtime proof intentionally skips real inference when provider is non-Mock to avoid out-of-contract spend. | Deploy logs | High | Real-provider quality/cost is optional evidence, never a claimed automated result |
| SEO / 3D / formal compliance | N/A: the core is a session research application; no public-content SEO outcome, 3D comprehension use case, regulated jurisdiction, or certification target exists. | Product/code review | High | Reopen only when repository evidence creates a core-user need |

Baseline artifacts:

- `output/evidence-sha256.txt`
- `output/playwright/goal-baseline-2026-07-26/`
- `output/playwright/m0-fixtures-2026-07-26/`
- `output/playwright/m1-fonts-2026-07-26/`
- `output/performance/`
- `output/security/`
- `output/anchor/annotation-anchor-contract-2026-07-26.json`
- `output/release/pr15-staging-proof-2026-07-26.json`

## 4. Invariants, Constraints, and Non-Goals

### Invariants

- Preserve Miniflux integration, existing public API shapes, database data, annotation metadata compatibility, shared-demo role behavior, Admin authorization, session invalidation, CacheStorage isolation, and export ownership.
- Preserve the current Next.js/React/FastAPI/SQLAlchemy/Alembic/PostgreSQL/Compose architecture unless a reproduced failure proves that a smaller local fix cannot satisfy a MUST gate.
- Keep generated OpenAPI and TypeScript artifacts synchronized.
- Keep secrets ignored, unread in evidence, least-readable in practical scope, and absent from Git/log artifacts.
- Keep production fail-closed. No autonomous run may mutate production, DNS, credentials, or irreversible user data.
- Maintain reduced-motion, keyboard, light/dark, current URLs, and backward-compatible annotation parsing throughout incremental work.
- Every behavior change updates `docs/learning-notes.md` and the evidence ledger as required by `AGENTS.md`.

### Non-goals

- No broad re-skin, Tailwind/shadcn migration, framework rewrite, speculative microservice, generalized design-system package, or file-size-only refactor.
- No decorative 3D, particles, gradients, glow, excessive rounding, or animation added to raise perceived quality.
- No production restoration/promotion, real-provider spend, full localization platform, SEO campaign, or invented compliance program.
- No dependency upgrade without an acceptance-mapped security, compatibility, or reproducibility need.
- No tracing platform unless current logs/metrics fail to diagnose a reproduced incident.
- No destructive data repair. Use copy-on-write fixtures, temporary databases, reversible migrations, and restored snapshots.

## 5. Evidence-Backed Opportunity Map

| Area | Current opportunity | User impact | Confidence | Autonomous intervention |
| --- | --- | --- | --- | --- |
| Core product loop | Capabilities exist, but one continuous Scan → Focus → Keep → Research rubric is incomplete. | Individually working modules may still fail as one daily workflow. | High | Build one deterministic cross-surface scenario and close its state/continuity gaps before adding features. |
| Knowledge capture | Initial anchor contract is green; ambiguity, content refresh, remaining input modes, retry, and user switching are incomplete. | Notes may attach incorrectly or disappear. | High | Test wrong-anchor cases first; add bounded restoration/rejection behavior without a migration unless evidence requires one. |
| State truth | Loading, empty, partial-error, retry, and stale combinations are not systematic across primary views. | Users can misread failure as absence or lose successful content. | High | Create a shared state matrix and one fixture per behavior class; preserve usable partial results. |
| Accessibility | Known light-theme token ratios can fail normal-text AA; complete audit is absent. | Required information may be unreadable or unannounced. | High | Add role-aware contrast tests and automated semantic audit; adjust the smallest token/usage scope. |
| Responsive/input | Six widths, touch-equivalent input, zoom/reflow, and two engines are incomplete. | Controls can collide or become unreachable. | High | Add pairwise coverage that maximizes state/width/input diversity without a full Cartesian explosion. |
| Visual craft | Identity exists; hierarchy/density/state polish is uneven. | Product can feel inconsistent despite strong foundations. | Medium-high | Use fixed fixtures and §8 rubric; improve evidence hierarchy and reading rhythm, not decoration. |
| Frontend performance | Static size improved; route/user timing and motion costs are unknown. | Work may optimize bytes without improving experience. | High | Measure five-run warm/cold baselines, derive budgets, then optimize only the largest repeatable bottleneck. |
| API/data/worker | Four PostgreSQL tests, restored-snapshot migration, and DB/queue concurrency evidence are missing. | SQLite-green behavior may fail under deployment conditions. | High | Use CI PostgreSQL or disposable local containers; run conditional tests, migrations, plans, and bounded concurrency. |
| Resilience | Recovery and degradation behavior is partly tested, not budgeted. | Transient failures may trap users or duplicate work. | High | Add timeout/retry/idempotency scenarios and measure recovery, preserving explicit failure after bounded retries. |
| Security/privacy | Main code gate is green; VPS secret metadata and session A→B proof remain. | Private state or operational details could escape. | High | Mode-only diagnostics, two-user fixtures, cache inspection, and redacted scanner summaries. |
| Observability | Metrics boundary is safe; alert semantics and correlation are incomplete. | Operators may see numbers without actionable diagnosis. | Medium-high | Assert metric families/labels, correlate request/job IDs, and reproduce one failure from logs before considering tracing. |
| Release/rollback | Exact PR deploy works; main closure, rollback rehearsal, and cleanup remain. | A release can succeed yet be hard to undo or retain safely. | High | Prove main SHA, previous immutable tag rollback, redeploy current tag, and cleanup dry-run before deletion. |
| Maintainability | Large hotspots exist without failure-linked extraction evidence. | Review cost and regression locality can degrade. | Medium | Extract only seams touched by an accepted behavior when tests show a clearer ownership boundary. |
| Documentation/DX | Current docs improved; one retired service remains in root rules and newcomer replay is absent. | Contributors may run an obsolete check. | High | Reconcile executable commands with current services and run them from a clean clone/worktree. |
| Cost/external services | Safe automation avoids real MiniMax spend. | Quality/cost trade-off remains unknown without risking credits. | High | Keep Mock/contract gates authoritative; optional capped evaluation never gates completion or claims unsupported quality. |
| SEO / 3D / formal regulation | N/A under current product evidence. | Work would consume scope without advancing the objective. | High | Keep excluded and re-evaluate only from new repository/user-outcome evidence. |

## 6. Prioritized Scope

Priority is recalculated after every milestone using `Value = Impact × Confidence ÷ (Effort × Risk)`, each factor scored 1–5 from current evidence. A higher P0/P1 acceptance failure always outranks cosmetic or speculative work.

### P0 — necessary for the primary objective

| Work | Acceptance | Why now | Dependencies |
| --- | --- | --- | --- |
| Complete the core-loop state and continuity matrix | A-02, A-07 | It is the product outcome, not a component detail. | Deterministic fixtures |
| Close annotation restoration, ambiguity, input, retry, and identity integrity | A-03, A-04, A-08 | Keep is a core action with privacy consequences. | Existing versioned anchor |
| Prove accessibility, responsive geometry, input, reduced motion, and cross-engine behavior | A-05, A-06 | Unreachable or unreadable UI invalidates the workflow. | Playwright engines/audit tooling |
| Establish nonzero Web/API/queue/DB baselines and resilience budgets | A-09, A-10 | Optimization and reliability claims need repeatable measures. | Synthetic dataset; disposable PostgreSQL |
| Execute PostgreSQL/migration/concurrency integrity | A-08, A-10 | Deployment data behavior cannot be inferred from SQLite. | CI service or local container |
| Close exact-main staging, rollback, and registry maintenance evidence | A-11, A-12 | Delivery is incomplete without reproducibility and recovery. | Existing workflow/GHCR |
| Preserve security, privacy, and current-truth documentation throughout | A-04, A-13, A-15 | These are cross-cutting trust controls. | Every milestone |

### P1 — strong quality increase with controlled risk

| Work | Acceptance | Why now | Dependencies |
| --- | --- | --- | --- |
| Unify visual/state hierarchy under the current editorial identity | A-07, A-14 | Improves comprehension after state correctness is stable. | Core fixtures; contrast fix |
| Improve request/job metric semantics and log correlation | A-10, A-13 | Makes failure recovery auditable without speculative tracing. | Reproduced failure scenarios |
| Extract failure-linked seams and deterministic developer commands | A-13 | Reduces review risk only where accepted work already proves a boundary. | P0 code changes |
| Tighten measured performance budgets after a stable baseline | A-09 | Prevents regression and focuses subsequent cycles. | Repeatability threshold met |

### P2 — optional excellence

- Additional browser/device samples after the required pairwise matrix.
- Optional capped real-provider quality/cost comparison through the existing adapter.
- Tracing only after a logged incident demonstrates that metrics/log correlation is insufficient.
- Additional visual narrative polish that scores higher under §8 without performance or accessibility loss.

### Deferred / N/A

- Production mutation, full i18n platform, public-content SEO, decorative 3D/effects, framework rewrite, speculative service split, and formal regulatory certification.

## 7. Acceptance Matrix

Status values in `PLANS.md`: `NOT_STARTED`, `IN_PROGRESS`, `PASS`, `REGRESSED`, `DEFERRED_NON_CORE`. There is no `BLOCKED`.

| ID | Outcome | Priority | Baseline | Target | Automated verification | Evidence | Pass condition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01 | Exact-SHA reproducibility | MUST | Evidence manifest and deterministic local/CI gates exist. | One clean exact revision reproduces all scoped commands and artifacts. | `git diff --check`; `shasum -a 256 -c output/evidence-sha256.txt`; full CI gate | SHA, versions, exits, counts, hashes | All commands exit 0; no untracked required artifact or unexplained drift. |
| A-02 | Truthful continuous core loop | MUST | Representative success and one Daily failure pass; full matrix incomplete. | Daily/Scan → Reader/Ask → Keep → Review/Research/Export preserves context through applicable load/empty/error/retry/stale states. | Tagged Playwright scenarios with deterministic fixtures and unexpected-console/page-error gate | State matrix, traces, screenshots | Every required state observed; usable partial data remains; no silent context loss or unexpected browser error. |
| A-03 | Dependable annotation flow | MUST | Versioned capture/editor-focus paths pass. | Mouse, touch-equivalent, and keyboard selection; repeated text; inline markup; refresh; retry; and restoration attach only to the intended passage or visibly reject/recover. | Unit/API tests plus tagged Playwright anchor scenarios | Synthetic payloads, traces | All scenarios pass; no wrong silent anchor; old metadata remains readable. |
| A-04 | Auth, privacy, cache, and secret boundary | MUST | Admin 403, session/cache tests, local 0600, Trivy green. | User A data cannot appear for user B/logout; Admin stays role-protected; public metrics stay denied; secrets never enter artifacts. | API auth tests; two-user browser fixture; CacheStorage inspection; Trivy; mode-only script; metrics smoke | Redacted boundary matrix | Expected 200/401/403/404 matrix; no cross-user residue; zero secret or unresolved high/critical finding. |
| A-05 | Accessibility and reduced-motion equivalence | MUST | Known contrast risks; partial keyboard/semantic coverage. | WCAG 2.2 AA for required UI; correct name/role/value/focus/error announcements; 200% reflow; reduced motion preserves information/actions. | Deterministic contrast roles; axe-compatible browser audit; keyboard/reflow/reduced Playwright scenarios | Audit JSON, semantic snapshots, screenshots | No serious/critical violation; required contrast passes; no hidden state/action in reduced mode. |
| A-06 | Responsive, input, and cross-browser core loop | MUST | Chromium partial coverage. | Anchor widths 320/390/768/1024/1280/1440, mouse/touch-equivalent/keyboard, Chromium/Firefox/WebKit pass a pairwise core matrix. | Playwright projects and geometry assertions | Matrix with engine/width/input/theme/motion | No overflow, collision, unreachable action, or engine-specific core failure; every required factor appears. |
| A-07 | Coherent product and visual state language | MUST | Warm editorial base; uneven hierarchy/state polish. | Core surfaces score at least 4 for task completion, hierarchy, state truth, and accessibility; no applicable §8 row below 3. | Fixed-fixture screenshot set; deterministic token/state checks; two automated rubric passes separated by a full regression run | Scorecards/contact sheet | Threshold met without decorative inflation; automated behavior gates remain green. |
| A-08 | API, schema, PostgreSQL, migration, and worker integrity | MUST | API 219; Worker 121 with 4 PG skips; clean Alembic upgrade. | No required PG skip; clean and restored-snapshot upgrade reach head; generated schema is exact; queue/data invariants hold. | API/Worker pytest with PG URLs; Alembic upgrade; OpenAPI export/client generation diff; migration snapshot script | CI logs, revision, sanitized DB summary | Zero unexplained skip/failure; migration and schema match; recovery point identified. |
| A-09 | Measured frontend/API/queue/DB performance | MUST | Static asset size known; route/DB values missing. | Five-run baselines are nonzero and stable; candidate has no material regression and each optimization shows a repeatable benefit. | Browser performance harness; API/queue/DB benchmarks; bundle report | Raw samples, median/p95, environment manifest | Coefficient/range repeatability ≤15% or documented noise model; candidate ≤110% of stable baseline p95 unless a larger user-visible gain is proven; optimization benefit ≥10% on its target metric. |
| A-10 | Resilience, recovery, and observability | MUST | Partial retries/metrics; no recovery budget. | Timeouts, retries, idempotency, partial degradation, queue restart, and one correlated failure are reproducible and truthful. | Fault fixtures; bounded retry tests; queue restart test; metric/log correlation assertions | Timings, redacted logs/metrics | No duplicate/lost accepted action; bounded recovery; terminal failure explicit; one incident traceable without secret data. |
| A-11 | Supply-chain and environment security | MUST | Production npm audit 0; Trivy green; action deprecation warning exists. | No unresolved high/critical production vulnerability or secret; deterministic versions; environment boundaries remain explicit. | `npm audit --omit=dev`; full audit; pinned Trivy; lockfile-family review; Compose/env validation | Audit summaries and CI URL | Zero production high/critical; development findings owned by an automated remediation/defer record; no secret or boundary regression. |
| A-12 | Reproducible staging release and rollback | MUST | Exact main SHA `969a077a` passes CI, three-image publication, staging deploy, migration, and smoke; rollback/cleanup remain. | Exact main SHA images deploy to staging; migrations/smoke/browser probe pass; previous immutable tag rollback and return-forward work; cleanup dry-run and one safe run succeed. | GitHub Actions; `smoke-test.sh staging`; image labels/digests; rollback rehearsal; cleanup dry-run | Run URLs, tags/digests, smoke/rollback summaries | All jobs green; deployed SHA matches main; rollback/forward both healthy; cleanup targets only intended versions; no production action. |
| A-13 | Maintainability, documentation, and developer experience | MUST | Current docs mostly aligned; hotspots/root rule drift remain. | A clean worktree/clone can follow current commands; changed seams have focused ownership/tests; no active contradictory instruction. | Link/command replay; `rg` retired claims; complexity/duplication only for touched seams; `git diff --check` | Replay log, doc truth matrix, focused diffs | Commands work; learning notes current; no unrelated refactor or stale active claim. |
| A-14 | Distinctive, purposeful craft | SHOULD | Editorial identity exists. | Evidence/citation/reading context is the signature across core pages; typography, density, copy, motion, and feedback score ≥4 where applicable. | §8 rubric and fixed contact sheet after all MUST behavior gates | Scorecards/screenshots | No score depends on gradients/glow/cards/particles/excess motion; no usability/performance/a11y regression. |
| A-15 | External-service and cost safety | MUST | Mock contracts pass; real MiniMax inference intentionally skipped. | Automation proves provider-independent behavior with Mock/contract adapters, enforces caps/timeouts/fallbacks, and never claims real quality without a real run. | Provider contract tests; Mock E2E; cap/timeout/fallback tests; redacted config-name inventory | Synthetic reports | All behavior gates pass without external credentials/spend; any optional real result is labelled, capped, redacted, and non-gating. |

## 8. Quality and Delight Rubric

Each row is scored 0–5 against identical synthetic fixtures and viewport/theme inputs. Automated assertions and artifacts take precedence over prose. A score cannot override a failed MUST gate.

| Dimension | 0–1 failure | 3 acceptable | 4 excellent | 5 exceptional | Evidence |
| --- | --- | --- | --- | --- | --- |
| Product task completion | Core loop breaks or loses work/context. | Main path completes with minor friction. | Every core state recovers clearly and context persists. | Complex partial failures still feel predictable and fast. | A-02/A-03 traces and task steps |
| Information hierarchy | Competing panels/actions obscure the task. | Primary action/content is identifiable. | Evidence, reading, and next action are immediately legible. | Hierarchy adapts to expertise/state without added complexity. | Fixed screenshots, semantic order, step count |
| Interaction clarity | Hidden modes, ambiguous controls, or false state. | Controls and outcomes are understandable. | Keyboard/pointer/touch feedback is consistent and truthful. | Recovery and edge cases teach themselves through concise feedback. | Input/state matrix |
| Visual consistency | Tokens/components conflict or look templated. | Core surfaces share a usable system. | Editorial typography, spacing, density, and state language are coherent. | The product is recognizable from evidence/reading rhythm alone. | Contact sheet and token checks |
| Brand distinctiveness | Generic dashboard decoration replaces product meaning. | Warm editorial identity is present. | Citation/evidence context forms a non-template signature. | Brand and task semantics reinforce each other at every surface. | Screenshot comparison and copy inventory |
| Motion/feedback | Jank, distraction, or reduced-mode loss. | Short feedback works and reduced mode is safe. | Motion explains causality using measured, safe properties. | Timing feels inevitable while remaining invisible to users who reduce motion. | Normal/reduced traces |
| 3D narrative | Decorative 3D harms reading/performance. | **N/A target:** no 3D and no missing comprehension capability. | If evidence later reopens it, a useful 2D fallback exists. | If reopened, it measurably improves a hard comprehension task. | N/A declaration or evidence-backed experiment |
| Performance/accessibility | Slow, unreadable, inaccessible, or unbounded. | Basic budgets and AA pass. | Stable low-friction behavior across required matrix. | Strong performance and access persist under degraded device/network/input. | A-05/A-06/A-09 |
| Error/empty/edge states | Blank, contradictory, destructive, or unrecoverable. | Major states exist. | Partial data, cause, retry, and ownership are explicit. | Recovery preserves progress and prevents repeated failure. | A-02/A-10 state matrix |
| Code/design maintainability | Changes require broad edits with weak tests. | Current commands/tests protect common work. | Touched seams have clear ownership and focused contracts. | New behavior typically lands as one small reversible slice. | Diff topology, replay log |

## 9. Milestones and Checkpoints

Milestones are finite. Each closes a coherent user outcome and leaves a reversible checkpoint.

### M0 — Contract and reproducible baseline

- **Goal:** make the merged repository, commands, fixtures, environment limits, and evidence exact and repeatable.
- **Inputs:** `AGENTS.md`, current `main`, this file, existing artifacts.
- **Scope:** evidence scripts/ledger, fixture truth, environment manifest, stale-contract repair.
- **Verify:** A-01 plus existing Reader/API/Worker/Compose gates.
- **Observable result:** every later claim can cite an exact SHA, command, result, and artifact.
- **Rollback:** evidence-only commit.
- **Update:** `PLANS.md`, evidence hashes, learning notes.

### M1 — Core-loop truth and knowledge integrity

- **Goal:** close A-02/A-03 across Daily/Scan, Reader/Ask, Keep, Review/Research/Export.
- **Inputs:** deterministic fixtures and current versioned anchor.
- **Scope:** smallest state/continuity/anchor/retry changes and tests.
- **Verify:** tagged unit/API/Playwright scenarios; unexpected-console gate.
- **Observable result:** the complete daily loop works and never silently loses/misanchors knowledge.
- **Rollback:** one behavior slice per commit; preserve backward anchor parsing.
- **Update:** state matrix, traces, anchor examples, learning notes.

### M2 — Accessible responsive interaction

- **Goal:** close A-05/A-06 without changing the established product identity.
- **Inputs:** M1 fixed fixtures; current warm editorial tokens.
- **Scope:** contrast roles, semantics, focus/reflow, responsive geometry, input and engine projects.
- **Verify:** contrast/audit/keyboard/reflow/reduced-motion/cross-engine matrix.
- **Observable result:** the core loop is readable and operable across required users/devices.
- **Rollback:** token/usage fixes and geometry fixes remain separate.
- **Update:** audit JSON, pairwise matrix, screenshots.

### M3 — Data, performance, and resilience

- **Goal:** close A-08/A-09/A-10 with nonzero, repeatable deployment-like evidence.
- **Inputs:** disposable PostgreSQL, synthetic dataset, M1 flow.
- **Scope:** PG tests/migrations, benchmark harnesses, fault fixtures, only measured optimizations.
- **Verify:** live-PG suites, migration rehearsal, five-run benchmarks, bounded fault/restart scenarios.
- **Observable result:** data correctness, latency, recovery, and diagnosis have enforceable budgets.
- **Rollback:** snapshot/previous migration/image; revert any complexity without ≥10% target benefit.
- **Update:** raw samples, environment manifest, plans, learning notes.

### M4 — Product craft and maintainable seams

- **Goal:** close A-07/A-13/A-14 after correctness/access/performance are stable.
- **Inputs:** fixed fixtures, baseline rubric, failure-linked hotspot evidence.
- **Scope:** hierarchy/density/copy/state polish; only justified seam extraction and executable docs.
- **Verify:** two rubric passes separated by full regression; clean-worktree command replay.
- **Observable result:** a distinctive research product that remains easy to change safely.
- **Rollback:** visual and seam changes independently reversible.
- **Update:** contact sheet, scorecards, doc truth matrix.

### M5 — Exact release, rollback, and maintenance closure

- **Goal:** close A-11/A-12/A-15 on one exact main revision.
- **Inputs:** all prior MUST gates.
- **Scope:** supply-chain refresh only if required, immutable images, staging deploy, rollback/forward, cleanup dry-run/run.
- **Verify:** full CI; exact SHA/digest; staging smoke/browser probe; rollback/forward; safe cleanup.
- **Observable result:** staging serves the proven revision and recovery is operational.
- **Rollback:** previous immutable healthy tag and database recovery point.
- **Update:** final evidence bundle and integrity manifest.

### M6 — Final audit and evolution handoff

- **Goal:** prove §13 success without changing acceptance semantics.
- **Inputs:** M0–M5.
- **Scope:** final diff, command replay, evidence integrity, risk disclosure, stale-claim removal.
- **Verify:** every MUST row links to exact-revision passing evidence; full gate rerun.
- **Observable result:** a new autonomous run can reconstruct the outcome from repository files alone.
- **Rollback:** no product change; reopen the failing milestone if any regression appears.
- **Update:** final `PLANS.md` state and decision/change log.

## 10. Autonomous Execution, Decision, and Recovery Protocol

### Work-selection loop

1. Read all applicable `AGENTS.md`, `GOAL.md`, `PLANS.md`, Git status/history, and the newest evidence.
2. Re-run the cheapest relevant baseline before mutation.
3. Mark stale facts explicitly; never carry an old SHA’s PASS to a new candidate.
4. Select the highest-value failing P0 item. Work on one principal bottleneck at a time.
5. Reproduce the failure or add the smallest failing test/benchmark first.
6. Prefer the smallest compatible change using the current architecture and existing dependency set.
7. Verify the focused gate, then all gates affected by the change.
8. Record before/after values, exact commands, environment, limits, and rollback.
9. Commit a focused reversible slice and push when remote validation materially improves evidence.
10. At each milestone, run the complete required matrix, audit the diff, update `PLANS.md`, evidence hashes, and learning notes.

### Automatic decision rules

- If two implementations satisfy the same gate, choose in order: fewer changed boundaries, lower data risk, fewer dependencies, smaller diff, stronger automated proof, lower runtime cost.
- Use the current warm editorial/terracotta direction; resolve token/accessibility defects within it instead of reopening an unevidenced palette debate.
- Use staging as the live delivery boundary. Production remains read-only/fail-closed and is never required for completion.
- Use Mock and provider-contract adapters as the authoritative automated AI gate. Optional real-provider evidence never replaces deterministic behavior tests.
- Reuse the existing internal app network for metrics while public exact paths remain denied; add a new network/token only if a reproduced threat or isolation test fails.
- Preserve metadata-backed versioned anchors until a measured query/integrity requirement justifies a reversible migration.
- Do not split a large file merely because it is large. Extract only a seam touched by accepted work when the extraction reduces diff/test coupling.
- Introduce no new dependency unless existing tools cannot satisfy a MUST gate after a recorded small experiment.

### Missing environment or external service

1. Detect availability without exposing secrets.
2. Substitute, in order: existing deterministic fixture → in-memory adapter → Mock provider → disposable local service/container → CI service.
3. Run every invariant and contract that does not require the missing system.
4. Label external-only evidence absent; do not fabricate it and do not mark its acceptance row PASS.
5. Continue the next independent highest-value item and periodically retry the unavailable gate with bounded backoff.

### Failure recovery

- Transient network/registry/runner failures: retry at most three times with exponential backoff and jitter; preserve the first error and final outcome.
- Deterministic test/build failure: stop expanding the diff, isolate the first failing layer, and repair or revert the current slice.
- Failed experiment: after two evidence-backed approaches fail the same gate, revert the experiment, record both causes, and choose the next simpler intervention.
- No measurable benefit: revert any optimization or abstraction that does not improve its target by at least the A-09 threshold without a separately proven user-visible gain.
- Migration/data risk: use a copied snapshot or disposable DB; require upgrade and recovery proof before retaining the change. Never execute an irreversible live repair.
- External-only dead end: contain it as `DEFERRED_NON_CORE` only when it is outside the primary objective; otherwise keep it `IN_PROGRESS`, use substitutes, and continue other gates. The whole goal does not become blocked.
- Regression after a milestone: mark the affected acceptance `REGRESSED`, return to the smallest owning milestone, and restore the last green checkpoint before new work.

### Continuous evolution

- Once a milestone is green, scan tests, audit output, benchmark trends, runtime warnings, issue history, and changed hotspots for the next evidence-backed bottleneck.
- Add work only when it maps to the primary objective, an acceptance row, or a necessary risk control.
- Tighten budgets only after at least two comparable stable baselines; never relax a MUST target to accommodate an implementation.
- Treat warnings such as action-runtime deprecation or transient 429s as maintenance candidates ranked by observed failure/risk, not automatic unrelated upgrades.
- Finish the defined goal when §13 succeeds. Further product expansion requires a new contract rather than silently making this goal endless.

## 11. Progress and Evidence Ledger

`PLANS.md` must maintain:

| Field | Required content |
| --- | --- |
| Exact candidate | Branch, full SHA, base SHA, clean/dirty status |
| Current milestone | One M0–M6 milestone and active acceptance IDs |
| Last green checkpoint | Commit/SHA and commands |
| Current validation | Pass/fail/skip counts and tool versions |
| Before/after metrics | Raw artifact paths and comparable environment |
| Current experiment | Hypothesis, smallest change, success/failure threshold |
| Recovery point | Revert commit, image tag/digest, DB snapshot/revision |
| Missing external evidence | Exact unavailable system and local substitute used |
| Known risks | Severity, evidence, containment, owning acceptance |
| Next action | Single highest-value executable step |

Evidence rules:

- Store only synthetic, redacted, non-secret content.
- Hash durable artifacts in `output/evidence-sha256.txt`.
- Keep screenshots/traces tied to exact fixtures, viewport, theme, motion, browser, and SHA.
- Record conditional skips as missing evidence, never as passes.
- Preserve old evidence for before/after comparison, but label historical SHA clearly.

## 12. Decision and Change Log

| Timestamp | Autonomous decision | Evidence and effect |
| --- | --- | --- |
| 2026-07-26 | Preserve the warm editorial/terracotta identity. | It is the implemented, screenshot-tested direction; old indigo wording is historical. Accessibility changes operate within this system. |
| 2026-07-26 | Make staging the live delivery boundary and keep production fail-closed/read-only. | Current workflow deploys staging; production probes return 502 and production mutation is outside the core research-workspace outcome. |
| 2026-07-26 | Use Mock/provider contracts for mandatory AI verification. | Staging MiniMax proof safely skipped paid inference; deterministic behavior and fallback can be fully tested without credentials or spend. |
| 2026-07-26 | Keep metrics internal through the existing environment alias and deny the public exact path. | PR staging smoke proves internal scrape success and public 404 without a new secret/service. |
| 2026-07-26 | Keep versioned anchors in existing metadata until evidence requires a migration. | Typed validation and editor-focus persistence pass without data-shape disruption; restoration gaps are testable at the domain/UI layer. |
| 2026-07-26 | Replace human-gated blocker semantics with automatic containment and substitution. | The goal can progress unattended while preserving safety, evidence integrity, and the core value ceiling. |

Future log entries record the timestamp, evidence, affected acceptance IDs, chosen/rejected alternatives, rollback, and any target tightening. They never record a silent MUST reduction.

## 13. Completion and Safe-Continuation Conditions

### Success

The goal is complete only when:

- every MUST row A-01–A-13 and A-15 is `PASS` on one exact revision;
- every required command and browser/data/release matrix passes with disclosed, non-secret evidence;
- the complete user-visible core loop and edge-state matrix is verified;
- PostgreSQL/migration, privacy, security, accessibility, performance, resilience, staging, rollback/forward, and registry-maintenance requirements pass;
- evidence artifacts verify against their integrity manifest;
- the final diff and active documentation contain no undisclosed material risk, stale instruction, unrelated refactor, or invented result;
- any unfinished SHOULD item is explicitly outside the core outcome and has not regressed a MUST gate.

### Safe continuation

Anything short of Success remains active:

- a transient failure is retried under §10;
- a deterministic failure returns to its owning milestone;
- a missing external system uses a substitute while other work continues;
- an unsafe production/destructive action is never attempted and does not block staging/local completion;
- an external-only non-core enhancement may become `DEFERRED_NON_CORE`;
- no implementation difficulty, elapsed time, warning count, or unavailable optional credential permits completion or a lower target.

There is no terminal `BLOCKED` condition in this contract.
