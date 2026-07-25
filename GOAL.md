# Project Optimization Goal

> Baseline date: 2026-07-26 (Asia/Taipei)<br>
> Baseline branch: `feat/frontend-excellence`<br>
> Baseline committed revision: `609724d7`<br>
> Contract status: **Prepared for maintainer review; execution has not started**

## 0. Document Contract

This file is the authoritative source for the project's optimization objective, scope boundaries, acceptance criteria, evidence requirements, and stop conditions.

- `AGENTS.md` governs long-lived engineering and verification rules.
- `PLANS.md` governs dynamic execution order, active work, blockers, and checkpoint status. It does not exist at this baseline and MUST be created when `/goal` starts.
- The subordinate package at `.claude/skills/frontend-excellence-goal/` is prior implementation context. It does not override this root contract, and its historical pass claims MUST be re-verified on the execution revision.
- No agent may weaken a MUST criterion, broaden a non-goal, or change the core product direction without maintainer approval.
- New evidence may raise a standard, correct an erroneous baseline, add a risk, or make a verification command more precise. Such changes MUST be timestamped in §12 and reflected in `PLANS.md`.
- A passing aggregate test count, a screenshot set, or subjective approval cannot waive a failed MUST item.
- Current user-owned uncommitted changes and project-local skills are not part of this contract's authorship and MUST NOT be overwritten, reverted, staged, or attributed to this contract.

## 1. Primary Objective

Make AI Reader a trustworthy daily research workspace for a self-hosting researcher or small research team: from entering the public demo or private session, through Daily Intelligence and Scan, focused reading and grounded AI help, private highlights/notes/review, search/research, and administrative health checks, the user can complete one continuous research loop without losing context or private data, being shown a false state, or being trapped by viewport, keyboard, failure, or deployment drift. The system is deliverable when every MUST criterion in §7 passes on one exact revision, the representative browser matrix and live-PostgreSQL/CI/staging gates are evidenced, the release is reproducible and rollback-ready, and no undisclosed material risk remains; that is the stopping point.

## 2. User-Visible End State

- A user can enter the intended environment, understand whether it is a public shared demo or a private production session, and move through **Scan → Focus → Keep → Research** without silent resets.
- Daily Intelligence, article workbench, focused reader, Review, Search, Research, Export, and Admin expose truthful loading, empty, partial-failure, full-error, retry, success, and offline/stale states where those states can occur.
- Reading context survives pagination, article return, browser back/forward, refresh, research-job resumption, and supported viewport transitions.
- Article selection works with mouse, touch-equivalent input, and keyboard. Pending selections survive editor interaction; existing annotations and load failures are visible; anchors do not silently attach to the wrong repeated passage.
- Private/session data never crosses users through CacheStorage, browser state, exports, annotations, or API behavior. Production remains fail-closed; the staging shared-demo boundary remains explicit; Admin remains role-protected.
- At 375–1440 px, light/dark themes, keyboard-only input, and reduced motion, primary controls remain reachable, focus order is predictable, fixed layers do not overlap, and required text meets WCAG AA contrast.
- The warm editorial reading identity remains recognizable and subject-specific. A single approved action accent, consistent typography, restrained purposeful feedback, and coherent async states replace competing or generic visual patterns.
- Motion explains state or spatial change and has an equivalent reduced-motion path. Decorative 3D, particles, glow, gradients, and animation are not used as substitutes for product clarity.
- Users experience no known release-blocking regression. Measured performance budgets are established before performance work; changes do not regress those budgets and improve only evidenced bottlenecks.
- Existing Miniflux, FastAPI, PostgreSQL, worker, scoring, sanitization, cost-cap, project-transition, export, and deployment contracts continue to work unless this file explicitly changes them.
- A same-repository change can pass deterministic CI, build immutable images, deploy the exact revision to staging, run migrations and smoke checks, and be rolled back. Production promotion remains a separate maintainer action.

## 3. Verified Baseline

“Current worktree” includes the five user-owned modified business files listed below. “Committed HEAD” means a detached clean worktree at `609724d7`.

| Dimension | Current state | Evidence | Confidence | Missing evidence |
| --------- | ------------- | -------- | ---------- | ---------------- |
| Git and ownership boundary | Branch `feat/frontend-excellence`; local HEAD equals `origin/feat/frontend-excellence` at `609724d7`; it is 27 focused commits ahead of `main@dec47f67`. Five user-owned business files are modified and `.agents/` is untracked. | `git status --short`; `git log main..HEAD`; `git rev-parse HEAD origin/feat/frontend-excellence` | High | Whether/when the user wants the in-progress annotation-anchor work included in execution |
| Stack and package tooling | Reader uses Node 22.23.0/npm 10.9.8, Next.js 16.2.7, React 19.2.6, TypeScript 6.0.3, and a tracked `package-lock.json`. API/Worker require Python ≥3.12 and use FastAPI/SQLAlchemy/Alembic with `uv run --isolated`; neither Python app has a lockfile. Runtime composition includes Caddy, Authelia, Reader Web, FastAPI, Worker, Miniflux, and PostgreSQL. | Runtime version commands; `package.json`/lockfile; both `pyproject.toml`; Compose files | High | Approved Python dependency/tool locking strategy; supported browser-engine versions |
| Prior delivered baseline | PR #14 was squash-merged to `main@dec47f67`; main CI run `29647166164` and staging smoke were recorded as passed on 2026-07-18. | `docs/session-handoff.md`; `gh run view 29647166164` | High for that revision, not current | Current branch has no GitHub Actions run and is not deployed |
| Current committed Reader Web | Clean `HEAD` passes 185 Node tests, production build/TypeScript, and 42 Chromium E2E tests. | Isolated worktree: `npm test && npm run build && npm run test:e2e`; exits 0 | High | Firefox/WebKit, full theme/motion/state/content matrix, clean-console assertion, representative fixtures for every primary view |
| Current dirty Reader Web | `npm test` passes 185 tests, but `npm run build` and `npm run test:e2e` fail because `selection` may be `null` at `src/lib/articles/selection.ts:61`. | Direct commands in current worktree; Next.js type-check output | High | Completion intent and tests for the user-owned anchor change |
| API tests | 217 tests pass with two SQLite adapter deprecation warnings. | `cd apps/api && uv run --isolated --with-editable . --extra dev python -m pytest tests -q` | High | Live-PostgreSQL API/migration execution on the current branch |
| Worker tests | 121 pass and 4 PostgreSQL-conditional tests skip. | `cd apps/worker && uv run --isolated --with-editable . --extra dev python -m pytest tests -q` | High | The four conditional tests on PostgreSQL for the current branch |
| Python lint/reproducibility | API Ruff reports 198 errors; Worker Ruff reports 51. Dev dependencies declare `ruff>=0.4`. Isolated resolution changed from Ruff 0.15.20 to 0.16.0 during this survey, demonstrating an unbounded gate. | `ruff check .` in both apps; `pyproject.toml`; `ruff --version` | High | Maintainer-approved deterministic tool strategy and the minimal source-fix scope |
| API schema | Clean committed HEAD regenerates identical OpenAPI. Current dirty API adds annotation `anchor` and therefore drifts from tracked `openapi.json`. | `python -m app.export_openapi`; `cmp`; diff at `ArticleAnnotationRequest.anchor` | High | Whether the user-owned API change will be completed and the generated TypeScript contract updated |
| Compose and shell configuration | Staging, production, and edge Compose configurations render from `.env.example`; tracked shell scripts pass `bash -n`. | Three `docker compose ... config` commands; shell syntax loop | High | Image build, container health, migration, and runtime tests because the local Docker daemon is unavailable |
| Database benchmark | The implemented DB performance benchmark reports `queries_measured: 0`; it is not a performance baseline. | `apps/worker/app/benchmark/db_perf.py` | High | Dataset, query scenarios, p50/p95, explain plans, concurrency, and thresholds: `NEEDS_BASELINE` |
| Frontend build footprint | Clean HEAD produces `.next/static` ≈ 8.2 MiB and `.next/standalone` ≈ 47 MiB on disk; largest emitted JS files are ≈ 288 KiB and emitted CSS ≈ 276 KiB. These are uncompressed filesystem sizes, not user timing. | `du` and per-file sizes after clean production build | High | Route-level transfer, compression, Web Vitals, CPU/memory, low-end device/network measurements: `NEEDS_BASELINE` |
| Visual system | Warm-paper/terracotta editorial system is implemented in light/dark themes. Desktop hierarchy is recognizable; the 1440 workbench leaves substantial unused space and the first item dominates. At 390 px, desktop shortcut hints remain visible and compete with sort controls. | Source tokens; screenshots in `output/playwright/goal-baseline-2026-07-26/` | Medium-high | Maintainer decision between current terracotta and old root-goal indigo; systematic rubric scoring across all primary pages |
| Accessibility | Semantic landmarks, named controls, focus-trap/menu tests, and a global reduced-motion rule exist. Static token calculation finds light `muted/bg` at 3.40:1, `muted/panel` at 3.71:1, and `accent/bg` at 4.23:1, so required normal-text use can fail AA. | Playwright accessibility snapshots; E2E keyboard tests; token contrast calculation; CSS media query | Medium-high | Automated axe-equivalent audit, required-text usage map, screen-reader pass, zoom/reflow, Firefox/WebKit |
| Motion | Most motion uses short shared durations; reduced-motion disables animation/transition and typewriter behavior checks media preference. CSS still contains width animation and several blur/backdrop-filter uses. | `globals.css`; `typewriter.ts`; source scan | Medium | Runtime frame/paint/long-task evidence: `NEEDS_BASELINE` |
| Browser fixture quality | The E2E suite passes, but its screenshot fixture returns `Not Found` for several Daily Intelligence sources and supplies incomplete article detail, producing five homepage console errors and an unrepresentative reader. | Playwright snapshots, console count, home/reader screenshots, `scripts/e2e-server.mjs` | High | Representative success/empty/error fixtures and a zero-unexpected-console gate |
| Frontend dependency security | `npm audit --omit=dev` reports 3 high production vulnerabilities; full audit adds 1 low transitive development vulnerability. The direct affected package is Next.js 16.2.7; remediation requires a dependency change. | `npm audit --omit=dev --json`; `npm audit --json` | High as of 2026-07-26 | Maintainer approval to upgrade; post-remediation test/build/E2E/Trivy evidence |
| Secret/privacy hygiene | Real `.env` was not read and is ignored, but its local mode is `0644`. No obvious tracked secret was found. | `.gitignore`; filename/mode-only inspection; tracked text scan | Medium-high | VPS file modes and secret-store state; those require read-only VPS diagnostics |
| API observability boundary | `/api/metrics` has no FastAPI auth dependency, Caddy sends all `/api/*` directly to FastAPI, and live staging returns 200 with queue, failure, scheduler, and LLM-account metric families. | `apps/api/app/main.py`; `infra/caddy/Caddyfile`; read-only live probe | High | Approved public/internal boundary and Prometheus scrape path; production route could not be verified because its upstream returned 502 |
| Live staging | `/`, `/api/healthz`, `/api/articles`, and `/api/metrics` returned 200; `/api/admin/usage/today` returned 403 for the demo user. | Read-only `curl` probes on 2026-07-26; no mutation or secret output | High | Exact deployed image SHA cannot be proven from the public response; deep runtime proof under real MiniMax was intentionally not run |
| Production | `https://ai-reader.blankhoney.xyz/api/articles` and `/api/metrics` returned 502. Production promotion was not part of the prior staging completion. | Read-only status probes on 2026-07-26 | High for observed status | Whether production is intentionally dormant, its desired SLA, and any VPS/DNS/Caddy cause: `NEEDS_USER_DECISION` / `NEEDS_BASELINE` |
| CI/CD maintenance | Latest `main` CI is successful. Scheduled GHCR cleanup run `29721686230` failed: package lookup returned 404 and the action reported `token owns package false`. | GitHub Actions read-only inspection and failed-step log | High | Correct package ownership/name/token model and a safe dry-run |
| Documentation/current architecture | `CLAUDE.md`, current Compose/Caddy, and runtime code agree on a fully public staging functional demo. README/TECHNICAL/SPEC-CICD and older `docs/spec` sections still describe protected shells, retired `apps/scorer-worker`, or Tailwind/shadcn migration. | Cross-document/source comparison | High | Which historical documents should be archived versus rewritten |
| Product task/time metrics | No observed user-task completion time, error rate, retention, or real-data workflow benchmark was collected. | No telemetry or study artifact exists | High | All such values are `NEEDS_BASELINE`; no target may be invented before measurement |

Baseline screenshots:

- `output/playwright/goal-baseline-2026-07-26/workbench-1440-light.png`
- `output/playwright/goal-baseline-2026-07-26/workbench-390-dark.png`
- `output/playwright/goal-baseline-2026-07-26/home-1440-light.png`
- `output/playwright/goal-baseline-2026-07-26/reader-1440-light.png`

The home and reader screenshots intentionally preserve fixture deficiencies; they are evidence of the current evaluation gap, not proof that the live backend returns those payloads.

## 4. Constraints and Non-Goals

### Required invariants

- Miniflux remains the upstream truth for feeds and entries. AI Reader owns derived intelligence and user state.
- Browser code never connects directly to Miniflux or PostgreSQL; writes go through same-origin FastAPI contracts.
- Every untrusted article/remote HTML path, including offline cache reads, passes through `sanitizeArticleHtml()`.
- Agent output remains `<think>`-stripped, Markdown-only, and raw-HTML-free.
- Current `saved → project` semantics, private annotation isolation, export ownership, and cost caps cannot be bypassed.
- Production stays fail-closed; staging may remain a shared public demo only with the current user-role/Admin boundary. Admin APIs remain `require_admin`.
- OpenAPI and generated TypeScript stay synchronized whenever API shape changes.
- Automated verification uses mock providers. Real LLM calls, provider changes, or spend require explicit approval.
- Existing databases, migration history `0001`–`0010`, deployed data, cookies, session contracts, backup identity, and immutable image-tag behavior must remain compatible.
- The supported implementation stack remains Next.js/React/TypeScript, FastAPI/Python, PostgreSQL/Alembic, the queue worker, Docker Compose/Caddy, and GitHub Actions.
- Existing user modifications listed in §3 are preserved until the user finishes, discards, or explicitly delegates them.

### Compatibility requirements

- Representative Chromium coverage is mandatory; Firefox/WebKit compatibility must at minimum be measured for the core loop before completion.
- Required viewport anchors are 375×812, 390×844, 768×1024, 899×900, 901×900, and 1440×1000.
- Both light/dark themes and normal/`prefers-reduced-motion` modes are first-class.
- Current URLs and durable context parameters remain backward compatible unless a migration/redirect is tested.
- Staging and production compose aliases, secrets, databases, cookies, and auth upstreams remain isolated.

### Prohibited incidental work

- No Tailwind/shadcn migration, framework rewrite, global-state rewrite, generic component-library replacement, search-engine/graph-database introduction, or unrelated backend redesign.
- Do not split large files merely because they are large. Extract a seam only when a changed flow, testability problem, or measured performance issue justifies it.
- Do not auto-fix all Ruff findings, mass-format, rename broad surfaces, or clean historical docs outside an approved milestone.
- Do not add modules, AI features, 3D, particles, glow, gradients, or animation merely to appear comprehensive or modern.
- Do not change production infrastructure, DNS, Caddy, data, secrets, or accounts during local optimization.
- Do not claim a user-time, latency, throughput, accessibility, or performance improvement without before/after evidence.

### Not solved in this goal

- Multi-tenant SaaS, social reading, a general notebook, real-time collaboration, native mobile apps, full offline-first data ownership, external search engines, graph databases, and advertising.
- A new recommendation/scoring model, unbounded corpus Agent, or new paid provider.
- Full localization product infrastructure. Chinese-first UI plus original-language content remains compatible; full locale coverage is Deferred.
- SEO work beyond basic correctness: the primary product is a session application, not a public content publication. **SEO = N/A** unless a separate public-content surface is approved.
- Decorative or narrative 3D: no current research task requires it. **3D = N/A** unless a tested use case materially improves comprehension.
- Formal sector-specific regulatory certification: no regulated use case or jurisdiction is defined. **Regulatory certification = N/A**; baseline privacy/security obligations still apply.
- Production promotion or restoration. The current 502 is disclosed, but production action requires a separate maintainer decision and credentials.

### Maintainer decisions required before affected work

1. **D-01 — Action accent:** approve preserving the implemented terracotta direction or restoring the old root-goal indigo direction. Until then, no palette migration; the acceptance target is one approved accent, not a guessed hue.
2. **D-02 — Dependency remediation:** approved on 2026-07-26 for the smallest compatible update after isolated `npm audit`, build, test, and E2E proof.
3. **D-03 — Production boundary:** decide whether production is intentionally dormant or belongs to a later promotion/restoration task. It is not a completion condition here.
4. **D-04 — Metrics trust boundary:** approved on 2026-07-26 as an exact public deny plus existing internal app-network scrape. Live deployment still follows the normal release authority boundary.
5. Any destructive migration, irreversible data repair, real-provider spend, new external service, public metrics exposure exception, or security-boundary relaxation.

## 5. Opportunity Map

| Area | Evidence-backed problem | User impact | Root-cause hypothesis | Confidence | Candidate intervention |
| ---- | ----------------------- | ----------- | --------------------- | ---------- | ---------------------- |
| Product value / core loop | The feature surface is broad, but no current end-to-end task rubric proves one continuous daily loop. | Users may encounter individually working modules that do not form a dependable workflow. | Prior goals optimized capability coverage before one stable outcome contract. | High | Make Scan → Focus → Keep → Research the only primary flow; add scenario-based browser and live-data proof. |
| Functional correctness | Current dirty selection-anchor work blocks build/E2E and drifts OpenAPI; committed FEX-19–22 remain unverified. | Annotation capture may lose or mis-anchor knowledge; branch is not releasable while dirty. | Selection range lifetime and API anchor shape are being added without a completed type/schema/test slice. | High | Finish or explicitly exclude the user-owned slice; add minimal anchor contract, repeated-text/inline-markup/refresh tests, schema sync. |
| Information architecture / efficiency | 1440 workbench underuses space; mobile shows desktop shortcut hints; many sidebar modules compete for attention. | Scan decisions are slower and narrow screens are noisier. | Desktop-first hint density and broad feature navigation are not prioritized by task/state. | Medium-high | Preserve module coverage but prioritize the core loop, adapt shortcut disclosure by input/viewport, and measure task steps before layout changes. |
| UI visual quality / brand | Current warm-paper/terracotta implementation conflicts with old indigo wording; muted light tokens can fail contrast; page polish varies by fixture/state. | Brand direction is ambiguous and required text may be hard to read. | Documentation and tokens evolved separately; state components were added incrementally. | High | Resolve D-01, keep one action palette, repair contrast at token/usage level, apply a stable visual-state rubric. |
| Motion / microinteraction | Reduced-motion support exists, but width animation and blur/backdrop effects lack runtime evidence. | Potential jank or unnecessary motion on weaker devices; reduced mode may not be behaviorally equivalent everywhere. | Motion was source-reviewed but not profiled as a system. | Medium | Add normal/reduced pairwise tests and frame/long-task baseline; retain only purposeful transform/opacity feedback. |
| 3D / narrative | N/A: no code, product requirement, or comprehension problem calls for 3D. | Decorative 3D would distract from reading and add cost. | Not applicable to the core research loop. | High | Keep N/A. Reopen only with an approved, testable comprehension use case and static fallback. |
| Responsive / cross-browser | Chromium covers key breakpoints, but Firefox/WebKit and full theme/state stress are unmeasured. | Layout, focus, sticky layers, or service-worker behavior may regress outside one engine. | E2E was built as a focused Chromium regression suite. | High | Representative cross-browser core-loop suite plus the required pairwise viewport/theme/motion matrix. |
| Accessibility / reduced motion | Keyboard semantics are well tested, but light muted/accent token ratios are below 4.5:1 for normal text; no full automated or screen-reader audit. | Low-vision and assistive-tech users may miss required information. | Token colors were chosen aesthetically without a usage-aware deterministic contrast gate. | High | Map required text roles, meet WCAG AA, add automated checks, zoom/reflow and manual screen-reader procedure. |
| Frontend performance / assets | Static output is measurable, but no route transfer, Web Vitals, CPU, or low-end baseline exists. | Optimization could chase file size without improving user experience. | Existing benchmark focuses on correctness; no repeatable performance harness. | High | First establish local/CI route and browser metrics; set budgets from baseline; optimize only the largest evidenced bottleneck. |
| Backend architecture / API boundary | API shape is generated, but public metrics bypass auth and dirty anchor work is unsynchronized. | Operational data can be exposed; frontend/backend can drift. | Caddy intentionally bypasses outer auth for all `/api/*`, while `/api/metrics` has no app auth/allowlist. | High | Define internal metrics path/auth; preserve user/Admin dependencies; enforce OpenAPI drift in the slice. |
| Data model / migrations / transactions | Migration chain exists, but current branch has no live-PostgreSQL proof and annotation anchors are encoded in content metadata rather than a typed column. | Data behavior may differ from SQLite tests; anchor evolution may become fragile. | Local convenience tests and minimal metadata encoding avoid migrations but reduce queryability/validation. | Medium-high | Run live PG tests first; use the smallest safe anchor representation; migrate only if reproduced failures justify it, with rollback/backup proof. |
| Concurrency / cache / DB performance | PWA session isolation and async race tests exist; DB benchmark measures zero queries and four Worker PG tests skip locally. | Queue/search/research behavior under contention is unknown. | Correctness was prioritized; benchmark scaffolding was not completed with representative data. | High | Establish query/concurrency dataset, execute conditional tests in CI, inspect plans and measure p50/p95 before any index/cache change. |
| Stability / recovery / degradation | FEX-17 is incomplete; mock screenshots expose fixture `Not Found` and incomplete reader payloads; console errors are not gated. | Users can see contradictory or unhelpful states, and evaluation can miss regressions. | Primary panels fetch independently, while fixtures and state vocabulary lagged module growth. | High | Complete the state matrix, shared copy/visual rules, retry ownership, representative fixtures, and unexpected-console failure gate. |
| Security / permissions / privacy | Three high production npm advisories; `.env` mode 0644; public operational metrics; production 502 prevents boundary verification. | Exposure, denial-of-service, information disclosure, or unsafe operations are possible. | Dependency patch drift, permissive local file mode, and coarse edge routing. | High | Maintainer-approved patch update, audit/Trivy gate, file-mode/runbook checks, protected/internal metrics, production diagnostics only if D-03 approves. |
| Tests / regression / evaluation | Strong Node/Chromium counts do not cover current dirty build, representative screenshots, all engines, live PG, real page states, or console cleanliness. | A “green” suite can coexist with an unreleasable worktree or misleading UI. | Tests were added per bug but not yet unified into a release contract. | High | M0 evidence manifest, exact-SHA gates, representative scenario tags, clean-console and conditional-environment reporting. |
| Logs / metrics / tracing | Prometheus text covers requests, queue, scheduler and LLM accounts, but its public boundary is unsafe/undecided; no tracing baseline. | Operators gain visibility at the cost of exposure, while cross-service diagnosis remains limited. | Metrics were added directly to the app without a scrape-network contract. | High | Protect metrics, verify alertable semantics, correlate job/request IDs in logs; tracing remains P2 only if logs/metrics cannot diagnose a reproduced issue. |
| CI/CD / release / rollback | Current branch has no CI run; unbounded Ruff now fails; GHCR cleanup fails 404; local Docker daemon unavailable. | The branch cannot be called releasable and registry retention may drift. | Tool constraints, package ownership assumptions, and current branch delivery evidence are incomplete. | High | Deterministic lint toolchain, same-repo PR CI, safe cleanup dry-run, immutable image/staging/rollback evidence. |
| Maintainability / developer experience | `globals.css` (3654 lines), `FocusedArticleReader.tsx` (1171), `ProductModules.tsx` (1104), repository adapters, and one E2E file are hotspots; there is no Reader lint/format script. | Focused changes are harder to review and regression locality is poor. | Feature growth accumulated in central files; size alone has not yet been linked to failures. | Medium-high | Extract only seams touched by accepted work, organize E2E by behavior if it improves ownership, add deterministic commands instead of broad refactors. |
| Documentation / config / onboarding | Public docs disagree on staging auth, old scorer service, frontend stack, and already-delivered gaps; `AGENTS.md` still names retired `apps/scorer-worker`. | Maintainers can apply the wrong security/deploy/test procedure. | Historical specs were retained as active-looking truth after architecture changes. | High | Define current truth sources, update or label historical docs, correct commands/boundaries, keep learning notes current. |
| SEO | N/A for authenticated/session research application; no public article-indexing requirement exists. | SEO work would not advance the core loop. | Product is not a public content site. | High | Keep Deferred/N/A; preserve basic metadata only. |
| Internationalization | Chinese-first labels and original content coexist, but full locale coverage is not defined. | Some users may see mixed copy; full i18n could consume scope without a target audience. | Product direction is Chinese-first, not locale-platform-first. | Medium | Preserve content-language behavior and prevent garbled/missing strings; defer full i18n pending audience decision. |
| Cost | Score/ask/agent caps and Admin metrics exist; no real-provider benchmark was run to avoid spend. | Cost remains bounded, but quality/cost trade-offs on real data are unknown. | Safe tests intentionally use mock providers. | High | Preserve caps; real-provider evaluation only with approved sample, budget, redaction, and stop limit. |
| Legal / regulatory | N/A: no jurisdiction, regulated workflow, or compliance target is specified. | Invented compliance work would be misleading. | Insufficient product/legal context. | High | Keep N/A; escalate if data residency, copyright, or regulated use becomes a real requirement. |

## 6. Prioritized Scope

Every P0/P1 item maps to at least one §7 acceptance ID.

### P0 — required for the primary objective

| Item | Acceptance mapping | Impact | Confidence | Effort | Risk | Dependency | Why now |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Establish exact-SHA baseline/evidence infrastructure and representative fixtures | A-01, A-02 | High | High | M | Low | None | Current tests cannot distinguish dirty-worktree failure, committed health, or fixture gaps without manual interpretation. |
| Restore a deterministic, green release gate | A-02, A-03, A-04, A-12 | High | High | M | Medium | D-02 for dependency update | Current lint, dirty build, security audit, and no-current-CI state block any release claim. |
| Protect privacy/operational boundaries | A-03, A-05, A-10 | High | High | M | Medium | Metrics scrape design; VPS proof later | Public metrics and dependency findings are material risks; existing session/cache/admin invariants must remain true. |
| Complete knowledge-capture integrity | A-06, A-10 | High | High | M–L | Medium | User-owned anchor work decision | Keep is part of the core loop and current work is incomplete/unreleasable. |
| Complete truthful primary-view states and continuity | A-07 | High | High | M | Low–Medium | Representative fixtures | FEX-17 is explicitly incomplete and screenshot fixtures hide true quality. |
| Prove responsive, keyboard, accessibility, theme, and reduced-motion behavior | A-08, A-09 | High | High | M | Low | D-01 for palette | These are user-visible completion conditions, not optional polish. |
| Prove live PostgreSQL, migrations, API/schema, worker and staging delivery | A-10, A-11, A-12 | High | High | M | Medium | CI/VPS secrets; no local Docker daemon | Local-only proof cannot establish deployability or data compatibility. |

### P1 — strong quality increase with controlled risk

| Item | Acceptance mapping | Impact | Confidence | Effort | Risk | Dependency | Why now |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Consolidate one approved visual/state language without a re-skin | A-07, A-09, A-13 | Medium-high | High | M | Low–Medium | D-01 | Current product has a distinct base, but conflicting accent contracts and uneven state presentation reduce trust. |
| Establish and protect frontend/API/DB performance budgets | A-11, A-14 | Medium-high | High that baseline is missing | M | Low | M0 measurement fixtures/data | Prevents speculative optimization and defines a measurable ceiling. |
| Repair current-truth documentation and onboarding commands | A-02, A-05, A-12, A-15 | Medium-high | High | M | Low | Architecture decisions complete | Stale security/deploy instructions are operational risk, not cosmetic debt. |
| Reduce only proven maintainability hotspots touched by accepted work | A-02, A-15 | Medium | Medium-high | S–M | Low–Medium | A reproduced review/test bottleneck | Keeps changes reviewable without turning the goal into a broad refactor. |
| Repair GHCR cleanup with dry-run proof | A-12 | Medium | High | S–M | Medium if deletion mis-scoped | Correct package ownership/token model | Scheduled retention is already failing; dry-run prevents destructive guessing. |

### P2 — excellence/differentiation enhancements

| Item | Impact | Confidence | Effort | Risk | Dependency | Why now or not now |
| --- | --- | --- | --- | --- | --- | --- |
| A subject-specific “evidence trail” signature tying citations, highlights, and research return context together | Medium | Medium | M | Medium | Core loop and anchors stable | Do only if usability evidence shows it strengthens research identity rather than adds decoration. |
| Purposeful transition polish for state/location change | Low–medium | Medium | S–M | Low | Motion baseline and reduced path | Eligible only after correctness, performance, and accessibility pass. |
| Request/job correlation improvements or tracing | Medium for operations | Medium | M | Medium | Reproduced diagnosis gap | Metrics/logs first; add tracing only if they cannot explain a real failure. |
| Full cross-browser visual-regression expansion beyond core scenarios | Medium | Medium | M–L | Low | Stable fixtures | Core-loop cross-browser is MUST; exhaustive coverage is P2 based on failures found. |

### Deferred

| Item | Reason not now |
| --- | --- |
| Production restore/promotion | Requires D-03, production credentials, live diagnostics, and external change authority; staging release is this goal's delivery boundary. |
| Full i18n | No approved audience/locale matrix; preserve Chinese-first plus original-language compatibility. |
| SEO/public content | N/A to the session application and primary objective. |
| 3D/particles/decorative effects | N/A to research comprehension; would add performance/accessibility cost. |
| Search engine, graph DB, Redis, framework or state rewrite | No measured bottleneck justifies added infrastructure. |
| Real LLM quality/cost benchmark | Requires explicit sample, privacy review, provider credential, and spend cap. |
| Delete old specs or legacy residue wholesale | Historical evidence may be useful; label/archive selectively after truth-source review. |
| Multi-user collaboration expansion | Does not improve the single continuous daily research loop required here. |

## 7. Acceptance Matrix

Priority `MUST` cannot be waived. `SHOULD` may remain incomplete only with maintainer approval recorded in §12 and without breaking a MUST outcome.

| ID | Outcome | Priority | Baseline | Target | Verification command or procedure | Evidence artifact | Pass condition |
| -- | ------- | -------- | -------- | ------ | --------------------------------- | ----------------- | -------------- |
| A-01 | Reproducible baseline and evidence manifest | MUST | Evidence is split across terminal output, stale FEX ledger, and partial screenshots. | `PLANS.md` and an exact-SHA evidence ledger record commands, environment, exits, counts, browser matrix, metrics, known limits, and before/after values. | Run M0 commands from clean exact revision; hash screenshots/reports; compare dirty vs committed state explicitly. | `PLANS.md`; `docs/goal-evidence.md`; `output/playwright/<sha>/` | No unlabelled assumption; every acceptance row links to current evidence or an explicit blocker. |
| A-02 | Deterministic local/CI code gate | MUST | Node 185 pass; clean HEAD build/E2E pass; dirty build fails; API/Worker tests pass; Ruff 198/51 failures under unbounded versions. | On the candidate revision, all scoped tests, lint, type/build, E2E, schema drift, compose, shell, and `git diff --check` gates pass under deterministic tool versions. | Reader: `npm test && npm run build && npm run test:e2e`; API/Worker pytest + Ruff; OpenAPI export/generation diff; Compose renders; shell syntax; `git diff --check`. | Command logs with tool versions and SHA; CI run URL | Every command exits 0; conditional skips are disclosed and executed in A-10; no unauthorized generated or dependency drift. |
| A-03 | Dependency/security gate | MUST | `npm audit --omit=dev`: 3 high, 0 critical; full audit adds 1 low. | No known high/critical production finding without an approved, time-bounded exception; Trivy has no unapproved HIGH/CRITICAL; invariants remain green after D-02 remediation. | `npm audit --omit=dev`; `npm audit`; CI Trivy; focused auth/sanitize/cache tests; review lockfile-only diff before source changes. | Audit JSON summary; advisory decision record; CI security job | D-02 approved; required patch applied; all regression gates pass; exceptions identify owner, rationale, expiry, and mitigation. |
| A-04 | Current worktree/annotation slice is releasable | MUST | Dirty TypeScript nullability failure and OpenAPI anchor drift. | User-owned slice is either completed with tests/schema evidence or explicitly excluded into a preserved separate worktree/commit; candidate worktree builds cleanly. | Targeted selection/annotation tests; Reader build/E2E; API pytest/Ruff; OpenAPI and generated TS drift; `git status --short`. | Focused diff and test log; ownership decision | No lost user change; no type/schema drift; candidate status contains only intentional files. |
| A-05 | Safe auth, privacy, metrics, secret, and environment boundaries | MUST | Cache/session/Admin tests exist; staging Admin 403; metrics public 200; `.env` mode 0644; production 502. | Production remains fail-closed; staging demo/Admin behavior remains explicit; public metrics are non-200 while an approved internal scrape works; secret files use least-readable practical modes; no secret enters evidence/Git. | API auth/cache tests; public status-only curls; internal Compose/VPS scrape; a secret scanner with redacted finding output; filename/mode-only checks; standard read-only VPS diagnostic prompt. | Security boundary matrix with redacted status only | Expected 200/401/403 matrix matches contract; metrics boundary approved and proven; no credential content captured; no production mutation. |
| A-06 | Dependable private selection and annotation flow | MUST | FEX-19–22 pending; dirty anchor work incomplete. | Mouse, touch-equivalent, and keyboard selection enter the same flow; editor actions retain the selection; existing annotations/error/retry are truthful; repeated text/inline markup/content refresh cannot silently highlight the wrong passage. | Unit/API contract tests plus Playwright scenarios tagged for selection, editor focus, load failure, repeated quote, refresh, session A→B. | Trace/screenshots and contract payload examples with synthetic data | All scenarios pass; wrong-anchor cases are rejected/recovered visibly; user isolation and sanitizer paths remain intact. |
| A-07 | Truthful core-loop state and continuity | MUST | FEX-12–18 mostly proven historically; FEX-17 incomplete; mock home/reader fixtures produce unexpected failures. | Every primary core-loop view has its applicable state matrix; browser history, pagination, article return, research resume, retry, and partial failure preserve context without contradictory states. | Playwright tagged scenarios for Daily, workbench, reader, Review, Search, Research, Export, Admin; fixture contract tests; unexpected console/page-error listener. | State matrix, screenshots, traces | Required states observed; successful data remains visible during partial failure; no unexpected console/page error; no silent context loss. |
| A-08 | Responsive, input, and cross-browser core loop | MUST | Chromium 42 tests pass at key widths; mobile shortcut hints remain visible; Firefox/WebKit unmeasured. | Representative core loop passes at all six anchor widths, mouse/touch-equivalent/keyboard input, with no horizontal overflow, fixed-layer collision, unreachable action, or inappropriate desktop hint. Chromium plus Firefox/WebKit core scenarios pass. | Playwright projects/matrix; keyboard-only manual checklist; 200% zoom/reflow procedure. | Pairwise matrix, screenshots/traces per engine | Every required width/input/engine appears in evidence; all P0 geometry/input assertions pass; exceptions require approved documented limitation. |
| A-09 | Accessible, coherent visual/motion contract | MUST | Strong editorial base; D-01 conflict; light muted/accent token risks; reduced-motion source rule exists. | D-01 resolves one action accent; required text meets AA; focus/name/role/value and error announcement are correct; light/dark and reduced motion are equivalent; rubric dimensions relevant to core flow score ≥4 with no applicable dimension <3. | Deterministic contrast test; accessibility browser audit; semantic snapshot; keyboard and screen-reader checklist; light/dark/reduced screenshots; §8 dual review by agent plus maintainer/sample user. | Audit report, token table, rubric scorecards, screenshots | No serious/critical accessibility violation; contrast threshold passes by role; no hidden action/state in reduced mode; rubric threshold met without decorative score inflation. |
| A-10 | API/data/worker integrity on real PostgreSQL | MUST | API 217 pass; Worker 121 pass/4 skip; clean OpenAPI matches; local Docker daemon unavailable. | PostgreSQL-conditional tests execute, migrations upgrade from supported baseline and on a restored snapshot, rollback procedure is documented/tested where safe, API/schema generated artifacts match, queue concurrency invariants hold. | CI PostgreSQL service; `alembic upgrade head`; API/Worker pytest with DB URLs; OpenAPI generation; migration smoke/backup identity checks. | CI logs, migration revision, sanitized DB test summary | Zero unexplained skip/failure in required PG tests; migration reaches head; no data-contract regression; rollback/recovery point identified before changes. |
| A-11 | Measured performance and resilience budgets | MUST | DB benchmark measures 0; web user metrics and API/queue p95 are `NEEDS_BASELINE`; static sizes only. | M0 records repeatable web/API/DB/queue baselines on representative synthetic data, then §12 approves budgets. Candidate shows no material regression; any optimization has measured benefit. | Repeatable browser performance script, bundle report, API/DB benchmark with dataset/iterations, query plans, queue test; compare identical environment. | Before/after JSON/CSV and environment manifest | Baseline is nonzero/repeatable; budgets are approved before optimization; candidate stays within them; complexity without benefit is reverted. |
| A-12 | Reproducible CI, staging deploy, rollback, registry maintenance | MUST | Last main CI/staging proof is `dec47f67`; current branch has no run; GHCR cleanup 404; production outside scope. | Same-repo candidate CI passes, exact-SHA images publish, staging deploy/migrations/smoke pass, deployed SHA is traceable, rollback target is proven, cleanup dry-run and subsequent scheduled/manual run succeed. | GitHub Actions jobs; `smoke-test.sh staging`; image label/tag inspection; rollback dry-run/procedure; `ghcr-cleanup` with `dry_run=true` before deletion. | Run URLs, workflow summary, image tags/digests, smoke/rollback/cleanup logs | All jobs green; staging exact SHA matches candidate; no prod action; cleanup selects only intended packages/versions before non-dry run. |
| A-13 | Distinctive product craft without template decoration | SHOULD | Warm editorial identity exists; hierarchy/space/state consistency varies; action palette conflict. | Core pages read as one AI research product, not a generic dashboard: evidence/citation/reading context is the signature; typography, density, copy, and state hierarchy meet §8 ≥4. | Stable screenshot set with identical fixtures; §8 scorecards from at least two passes separated in time, one including maintainer/sample user. | Before/after contact sheet and signed scorecards | No score comes from gradients/glow/rounding/particles/excess motion; ≥4 on relevant craft rows and no core usability regression. |
| A-14 | Frontend motion/resource performance | SHOULD | Static output 8.2 MiB; runtime motion costs `NEEDS_BASELINE`. | Approved transfer/interaction/long-task budgets pass in normal and reduced modes; animations use compositor-safe properties unless measured exception; no layout shift from loading transitions. | Browser performance trace; computed-style/long-task checks; bundle diff; normal/reduced Playwright scenarios. | Trace files, metric JSON, bundle report | Budgets pass; reduced mode removes nonessential motion; no unapproved layout-triggering hot loop or material regression. |
| A-15 | Current-truth docs and maintainable change surface | MUST | Security/deploy/frontend/legacy-service docs conflict; central files are large. | README/technical/deploy/security/onboarding commands match code and GOAL; historical specs are clearly labeled; learning notes record durable discoveries; only justified seams are extracted. | Link/command review; `rg` for retired claims; run documented commands; diff review against task scope. | Documentation truth matrix; final diff review | No known contradictory active instruction; new member can run gates from docs; no unrelated refactor or stale acceptance claim. |

## 8. Quality and Delight Rubric

Scoring happens against fixed synthetic fixtures and the same viewport/theme set before and after. Each applicable dimension is scored independently. “5” is not required for completion; A-09/A-13 define the threshold. 3D is N/A by default and excluded from the aggregate unless a separate maintainer decision explicitly introduces a product use case.

| Dimension | 0–1: failure | 3: acceptable | 4: excellent | 5: exceptional | Evidence and evaluation |
| --- | --- | --- | --- | --- | --- |
| Product task completion | Core loop breaks, loses work, or requires undocumented recovery. | Core loop completes in the happy path with understandable recovery. | Core loop remains complete across history, partial failure, and supported inputs with low avoidable friction. | Users can confidently triage, understand, capture, resume, and export while the system anticipates the next relevant action without hiding control. | Scenario success/steps/errors; Playwright traces; maintainer/sample-user task observation. No invented time target. |
| Information hierarchy and interaction clarity | Current location/state/action are ambiguous; competing controls dominate. | Primary action and state are identifiable; navigation is usable. | Scan/Focus/Keep purpose, priority, and next action are immediately legible at every anchor width. | Dense research information feels calm; progressive disclosure serves novice and power user without parallel mental models. | Screenshot rubric, keyboard path, action count, first-click/task-observation notes. |
| Visual system consistency | Mixed palettes/components/spacing; required text unreadable. | Shared tokens and patterns cover common surfaces with minor drift. | One approved palette, editorial typography, spacing, borders, controls, and async states are consistent in light/dark. | The system is recognizably AI Reader from an isolated crop while remaining content-first and accessible. | Token audit, screenshot contact sheet, contrast results, component-state inventory. |
| Brand distinctiveness / non-template quality | Generic admin-card dashboard or decorative trend collage. | Warm editorial identity is present but not consistently tied to product meaning. | Reading, evidence, score, citation, and research-return patterns form a subject-specific identity. | Product structure itself communicates “self-hosted evidence-led research,” not merely its logo or color. | Blind screenshot review prompt, evidence-flow walkthrough, before/after rubric. |
| Motion purpose, rhythm, feedback | Motion distracts, blocks, janks, or ignores reduced preference. | Short feedback exists and reduced mode disables nonessential motion. | Every motion explains state/spatial change, uses a consistent rhythm, and remains smooth/equivalent when reduced. | Motion subtly teaches the research workflow and improves orientation with no measurable cost or accessibility debt. | Normal/reduced recordings, traces, computed properties, task observation. |
| 3D and product narrative | Decorative 3D obscures reading or adds cost. | **Current N/A target:** no 3D and no missing comprehension capability. | If later approved, 3D explains otherwise hard-to-read relationships and has a complete 2D fallback. | If later approved, it is integral to a validated research task, performant, navigable, and accessible—not decoration. | N/A declaration. If reopened: approved use case, task comparison, performance/a11y and 2D fallback proof. |
| Performance, accessibility, reduced-motion degradation | Slow/unmeasured critical path; inaccessible actions; reduced mode loses information. | Baselines exist; core checks pass; no severe accessibility failure. | Approved budgets, WCAG AA, keyboard/reflow/cross-browser, and reduced equivalence all pass with clear evidence. | Experience remains immediate and comprehensible on constrained devices/networks and diverse access needs, with graceful degradation. | A-08/A-09/A-11/A-14 artifacts and environment manifest. |
| Error, empty, and abnormal-flow completeness | False empty/success/loading; dead ends; successful partial data discarded. | Primary errors and empties are distinct and offer a next step. | Each applicable state is truthful, local failures are isolated, retries preserve context, and stale/offline is explicit. | Recovery language and controls make failure feel designed, auditable, and low-risk without overwhelming normal use. | State matrix, failure injection, console/page-error gate, copy review. |
| Code/design-system maintainability | Changes require broad edits, duplicate state semantics, or fragile selectors. | Tests and tokens cover common behavior; ownership is understandable. | Changed seams are focused, typed, documented, and reusable only where repetition is proven. | New state/interaction can be added with a small coherent diff and deterministic evidence, without central-file growth or aesthetic drift. | Diff locality, dependency graph, test ownership, documented command success, reviewer rubric. |

Score discipline:

- A score cannot rise because of more gradients, glow, rounded cards, particles, shadows, or animation.
- A score cannot rise on screenshots while task completion, accessibility, performance, or truthful state regresses.
- Each score records fixture, viewport, theme, motion mode, evaluator, timestamp, and evidence path.
- The same evaluator reruns the baseline rubric after implementation; at least one final pass comes from the maintainer or a separate sample user.

## 9. Milestones and Checkpoints

### M0 — Baseline and evaluation infrastructure

- **Goal:** turn every `NEEDS_BASELINE` needed for decisions into a repeatable measure, and make evidence exact-SHA and representative.
- **Inputs/dependencies:** current branch; user-owned dirty-worktree decision only for candidate selection; no product change.
- **Expected modification scope:** `PLANS.md`, evidence ledger/scripts, Playwright fixtures/projects/reporting, benchmark harness/config, documentation of environment.
- **Verification:** A-01 commands; clean committed Reader/API/Worker gates; fixture screenshots; console listener; live-PG/engine availability recorded.
- **Observable result:** one command/procedure set reproduces correctness, state, accessibility, performance, and delivery baselines without confusing fixture failure with product failure.
- **Rollback point:** one focused M0 commit; evidence scripts can be removed without data/schema changes.
- **Docs/evidence update:** `PLANS.md`, `docs/goal-evidence.md`, `docs/learning-notes.md`, `output/playwright/<sha>/`.

### M1 — Release gate and security boundary

- **Goal:** make the candidate deterministic, buildable, schema-synchronized, and free of unapproved high/critical security findings; close the metrics/privacy decision.
- **Inputs/dependencies:** M0; D-02; user-owned anchor slice disposition; approved internal metrics design.
- **Expected modification scope:** minimal dependency/tool constraints, scoped Ruff/source fixes, current dirty type/schema completion if delegated, metrics edge/API rule, focused tests/runbooks.
- **Verification:** A-02–A-05; audits; auth/sanitize/cache tests; public/internal status matrix; no secret content read.
- **Observable result:** local and CI-equivalent gates agree; a public caller cannot read operational metrics; release blockers are explicit and green.
- **Rollback point:** separate commits for tool determinism, dependency remediation, and metrics boundary; retain prior lockfile/image tag.
- **Docs/evidence update:** dependency/security decision, active versions, boundary diagram, learning notes.

### M2 — Core-loop truth and knowledge integrity

- **Goal:** close annotation selection/anchor integrity and every primary-state/continuity gap in Scan → Focus → Keep → Research.
- **Inputs/dependencies:** M0 fixtures; M1 stable gate; user-owned work authorization.
- **Expected modification scope:** focused Reader components/hooks, minimal FastAPI/repository contract if required, state/retry copy, Playwright scenarios.
- **Verification:** A-06/A-07 plus API/schema conditional gate; no broad component rewrite.
- **Observable result:** selection/annotation survives supported input and content edge cases; all core views tell the truth and preserve context.
- **Rollback point:** one behavior slice per commit; schema/data change, if justified, has backup and reverse/forward plan before migration.
- **Docs/evidence update:** state matrix, anchor decision, API contract, screenshots/traces, learning notes.

### M3 — Accessible, responsive visual contract

- **Goal:** apply the approved single accent and coherent state language while meeting cross-browser, contrast, focus, responsive, and reduced-motion criteria.
- **Inputs/dependencies:** D-01; M2 stable flows; M0 rubric baseline.
- **Expected modification scope:** design tokens and their proven usages, responsive hint/layout fixes, shared primitives only where duplication is demonstrated, accessibility tests.
- **Verification:** A-08/A-09/A-13; §8 scorecards; all existing behavior gates.
- **Observable result:** the same AI Reader identity and complete core flow at all anchor widths/themes/motion modes, with AA required text and no decorative inflation.
- **Rollback point:** token/primitive/page polish commits remain separable; screenshot/metric regressions revert the responsible slice.
- **Docs/evidence update:** approved palette decision, token table, browser matrix, contrast/a11y report, rubric.

### M4 — Measured performance, resilience, and maintainability

- **Goal:** set budgets and improve only the dominant measured user/operation bottleneck; align current-truth docs and repair registry maintenance.
- **Inputs/dependencies:** M0 metrics; M1–M3 stable behavior; approved budgets.
- **Expected modification scope:** one measured bottleneck at a time, necessary indexes/query/UI asset seam, scoped code extraction, docs, GHCR workflow.
- **Verification:** A-11/A-12/A-14/A-15; before/after identical environment; cleanup dry-run.
- **Observable result:** no-regression budgets pass, at least one justified bottleneck has measurable benefit or is documented as already acceptable, docs/cleanup are current.
- **Rollback point:** performance changes are isolated; no-benefit complexity is reverted; cleanup remains dry-run until target list is reviewed.
- **Docs/evidence update:** metric datasets/reports, query plans where applicable, truth matrix, learning notes, cleanup selection log.

### M5 — Release-candidate and staging proof

- **Goal:** prove one exact revision from clean diff review through CI, images, migration, staging smoke, and rollback readiness.
- **Inputs/dependencies:** all prior MUST gates; GitHub/VPS staging authority already available to workflow; production explicitly excluded.
- **Expected modification scope:** evidence/docs and only release-blocking fixes.
- **Verification:** full A-01–A-15 gate; same-repo CI; exact image tag/digest; staging deploy/migrations/smoke; post-deploy read-only core-flow browser check; rollback target.
- **Observable result:** staging serves the exact candidate revision and all MUST evidence is reviewable from the ledger.
- **Rollback point:** previous immutable staging image tag/digest and documented migration recovery point.
- **Docs/evidence update:** final ledger, `PLANS.md`, learning notes, deployment summary, unresolved risks.

## 10. Execution Protocol

Every later Goal run MUST:

1. Measure before modifying.
2. Address one primary bottleneck at a time.
3. Keep each change focused, reviewable, and reversible.
4. Run the most relevant verification after every change.
5. Run the complete milestone gate at milestone end.
6. Record before/after data with revision, environment, command, and artifact path.
7. Revert complexity that produces no measurable benefit.
8. Never silently change an acceptance criterion.
9. Never mark the goal complete because implementation is difficult.
10. Pause and ask the user when facing an irreversible decision, data risk, missing secret/authority, or product-direction conflict.

Additionally:

- Start by reading `AGENTS.md`, this file, `PLANS.md`, current Git status, and the latest evidence ledger.
- Preserve user-owned dirty files. If overlap is unavoidable, use an isolated worktree or request direction.
- For a code-level bug with clear input/output, add the smallest failing test first.
- API-shape changes require OpenAPI and generated TypeScript synchronization in the same slice.
- Database changes require backup/restore and forward/reverse reasoning before migration execution.
- Use mock providers for automated tests; never spend real provider budget without an approved cap.
- Do not commit, push, open/merge a PR, deploy, change production, or delete registry/data merely because this file describes those checkpoints; external mutations still require the authority applicable to that run.
- Update `docs/learning-notes.md` whenever behavior, architecture, deployment, process, or reusable debugging knowledge changes.

## 11. Progress and Evidence

| Field | Current value |
| --- | --- |
| Current milestone | **M1 — IN_PROGRESS; all three approved mutations pushed; exact-candidate CI and live metrics proof remain** |
| Completed items | Repository/document/code/security/design/CI reconnaissance; exact-SHA plan/ledger; representative eight-surface E2E success fixture and unexpected-console gate; repeatable Web/API/queue/DB procedures; environment inventory; SHA-256 evidence manifest; deterministic Ruff; self-hosted licensed Newsreader delivery; bilingual current-truth docs; local `.env` mode 0600; explicit Trivy secret gate with 0 local findings; D-02 production audit remediation; D-04 public-deny/internal-scrape implementation; typed annotation-anchor contract and schema synchronization; A-01 and A-04 passed |
| Current validation state | Current candidate: production npm audit 0; full audit only 1 development low; Reader 189/build/45 Chromium; API 219/Ruff; Worker 121/4 PostgreSQL skips from M0; OpenAPI/generated TypeScript drift-free; D-04 static/API/Compose gates green; local Caddy/Docker live proof unavailable; same-repository CI pending |
| Evidence paths | This §3; `PLANS.md`; `docs/goal-evidence.md`; `output/evidence-sha256.txt`; `output/playwright/goal-baseline-2026-07-26/`; `output/playwright/m0-fixtures-2026-07-26/`; `output/playwright/m1-fonts-2026-07-26/`; `output/performance/`; `output/security/`; `.claude/skills/frontend-excellence-goal/evidence.md` as historical only |
| Latest measured metrics | Native static output 8,424→1,816 KiB and WOFF2 assets 107→2 for the M1 font candidate; standalone 39,084 KiB; clean browser behavior 43/43; light token ratios 3.40/3.71/4.23 candidates below normal-text AA; live DB/project Web Vitals `NEEDS_BASELINE` |
| Unresolved issues | D-01 accent; D-03 production intent; exact-candidate CI; D-04 live public/internal proof; GHCR cleanup 404; live PG/cross-browser/project performance baselines; anchor-aware restoration after refreshed content |
| Next highest-value action | Run the complete exact-candidate local gate, inspect same-repository CI for the pushed branch, then deploy the approved D-04 candidate only through the existing release workflow |

Evidence retention rules:

- Evidence identifies the exact Git SHA and whether the worktree was clean.
- Generated screenshots/reports are not silently committed. The final evidence ledger says which artifacts are tracked, ignored, or CI-hosted and their retention lifetime.
- No evidence contains cookies, tokens, API keys, `.env` contents, private article content, real annotations, user databases, or provider prompts.
- Historical evidence is never rewritten to imply it ran on a newer revision.

## 12. Decision and Change Log

| Timestamp (Asia/Taipei) | Type | Record | Consequence |
| --- | --- | --- | --- |
| 2026-07-26 | Discovery | Current execution branch contains 27 committed frontend-excellence changes plus five user-owned modified business files. | Contract distinguishes clean committed HEAD from dirty current worktree and forbids overwriting user work. |
| 2026-07-26 | Decision | Replace the old unlimited “research OS / optimize everything” goal with one continuous daily-research-loop outcome and finite milestones. | Every P0/P1 item must map to §7; unrelated product expansion is Deferred. |
| 2026-07-26 | Discovery | Clean HEAD passes Reader tests/build/E2E while dirty worktree fails build/E2E on one nullability error. | Both facts remain visible; neither is generalized into a false all-green/all-red claim. |
| 2026-07-26 | Discovery | Unbounded Ruff resolution produced a red gate and changed versions during isolated runs. | Tool determinism is P0 before broad lint repair. |
| 2026-07-26 | Discovery | Live staging exposes operational metrics publicly; production probes return 502. | Metrics protection is P0; production action is excluded pending D-03. |
| 2026-07-26 | Discovery | Browser tests pass but principal-page fixtures create unexpected console errors and unrepresentative home/reader screenshots. | M0 must repair evaluation fidelity before visual scoring or state completion claims. |
| 2026-07-26 | Execution | `/goal` activated M0; created `PLANS.md` and `docs/goal-evidence.md` while preserving the five user-owned business changes. | A-01 is in progress; browser fixture and performance baseline slices are next. |
| 2026-07-26 | Execution | Added representative default fixtures for eight principal surfaces, explicit Daily failure injection, and an unexpected `console.error`/`pageerror` gate. | M0.2 passes 43 Chromium scenarios; A-07/A-13 advance but remain incomplete. |
| 2026-07-26 | Discovery | A clean native Next build can fail when `next/font/google` cannot reach Google Fonts; a webpack/local-font-mock build proved source behavior but is not valid visual/performance evidence. | Deterministic font delivery is a release-gate risk; no timing number may be inferred from the mocked build. |
| 2026-07-26 | Execution | Added a read-only fixed-iteration JSON Web performance harness and validated its schema twice against a local fixed page. | The procedure exists; AI Reader route values remain `NEEDS_BASELINE` because external Chromium navigation is currently closed and the local native build is not deterministic. |
| 2026-07-26 | Execution | Added repeatable synthetic API/in-memory-queue procedures plus a read-only PostgreSQL procedure that exits `NEEDS_BASELINE` without a URL; inventoried engines/services/GitHub transport. | M0 now distinguishes measured code-path baselines from missing live infrastructure evidence. |
| 2026-07-26 | Checkpoint | Verified ten evidence artifacts against `output/evidence-sha256.txt`, audited acceptance links, and passed `git diff --check`. | M0 is complete and A-01 passes; M1 starts with deterministic Ruff tooling. |
| 2026-07-26 | Execution | Ruff 0.14.11/0.15.22 are clean while 0.16.0 introduces API 200/Worker 54 findings; both dev extras now pin the verified 0.15.22. | The lint gate is deterministic without broad source churn; M1 proceeds to build-time font delivery. |
| 2026-07-26 | Execution | Replaced build-time Google Fonts imports with two licensed project-local Newsreader variable subsets; retained the existing CJK system serif fallback. Two native builds are identical, Node/E2E are green, and static output drops 8,424→1,816 KiB. | Frontend production builds no longer require live font downloads; no dependency or unrelated visual-system change was introduced. |
| 2026-07-26 | Discovery | Current audit maps to Next 16.2.7, PostCSS 8.4.31, and Sharp 0.34.5. Next 16.2.11 fixes direct advisories but its declared transitive versions keep the dry-run audit at 3 high. | D-02 requires scoped compatibility testing or an owned expiring residual exception; no lockfile change was made. |
| 2026-07-26 | Change proposal | D-04: block public `/api/metrics` at the exact Caddy path while preserving environment-alias scraping over the existing app network. | Maintainer must approve the shared app network as the internal trust boundary before edge implementation; dedicated-network/token alternatives remain available. |
| 2026-07-26 | Execution | Corrected tracked English/Chinese staging-demo and CI contracts, labelled retired local specs/runbooks, changed local `.env` 0644→0600 without reading it, and documented the secure setup mode. | A-15 advances and the local secret boundary improves; live VPS mode and final candidate review remain. |
| 2026-07-26 | Execution | Verified a clean candidate snapshot with checksum-validated Trivy 0.69.3 secret scanning (0 findings) and made the CI scanner/tool version explicit. | Secret detection no longer relies on a mutable default; vulnerability remediation and final same-repo CI remain separate gates. |
| 2026-07-26 | Blocked | Three consecutive Goal turns reached the same authority boundary after all safe pre-decision work completed: D-02 for A-03, anchor ownership for A-04/A-06, and D-04 for A-05. | Goal execution pauses without dependency, Caddy/live, or user-owned-file mutation. Evidence and rollback points remain intact; resume requires the maintainer to approve `1`, `2`, and/or `3`. |
| 2026-07-26 | Decision | Maintainer replied `123全都批准`, approving D-02 dependency remediation, D-04 exact public metrics denial with internal app-network scraping, and completion of the five preserved annotation-anchor files. | Goal execution resumes at M1. Each slice remains independently reversible and must pass its own verification before the next slice begins. |
| 2026-07-26 | Rejected approach | Broad UI re-skin, Tailwind/shadcn migration, file-size-driven refactor, decorative 3D/effects. | None advances the primary objective without evidence; all remain prohibited/deferred. |
| 2026-07-26 | Change proposal | D-01: current terracotta versus historical indigo. | Maintainer approval required before M3 palette implementation. |
| 2026-07-26 | Approved change | D-02: patch vulnerable frontend dependencies with the smallest compatible isolated candidate. | Post-update audit, focused security checks, unit tests, build, E2E, and lockfile review are mandatory. |
| 2026-07-26 | Decision implemented | D-02 shipped on the branch as Next 16.2.11 with minimum fixed PostCSS 8.5.18 and Sharp 0.35.0 overrides. | Isolated production audit 0, Reader tests/build/E2E, and lockfile family review pass; remove overrides when upstream declarations make them unnecessary. |
| 2026-07-26 | Decision implemented | D-04 shipped on the branch as exact public `/api/metrics` 404 handlers plus worker-to-environment-alias internal scrape checks. | Static/API/Compose proof passes; live public 404 and internal 200 remain mandatory after deployment. |
| 2026-07-26 | Decision implemented | The five delegated annotation-anchor files were completed as a typed versioned text-quote contract with bounded context and offsets. | Anchor-only persistence, invalid-shape rejection, editor-focus survival, OpenAPI/generated client sync, API 219, Reader 189/build/45 Chromium pass; refreshed-content restoration remains M2 scope. |
| 2026-07-26 | Change proposal | After M0, add measured performance budgets to A-11/A-14. | This may correct `NEEDS_BASELINE`; it may not weaken other MUST criteria. |

Future entries MUST include timestamp, evidence, decision owner, affected acceptance IDs, and rollback implications. Proposed acceptance changes remain proposals until the maintainer approves them.

## 13. Stop and Escalation Conditions

### Success

The Goal may stop as successful only when:

- all MUST acceptance items pass;
- all required verification commands pass on the exact candidate revision;
- user-visible flows are verified through the representative browser matrix and staging proof;
- regression, security, privacy, data, and compatibility requirements are satisfied;
- evidence artifacts and before/after metrics are saved and linked;
- the final diff, generated artifacts, dependency changes, migrations, image identity, and rollback point have been reviewed;
- no undisclosed material risk remains;
- production has not been changed unless separately authorized. Production being outside scope is disclosed, not represented as production success.

### Blocked

Pause and ask the user when any of the following applies:

- a required secret, production permission, external account, or environment authority is missing;
- an irreversible data operation or destructive registry/infrastructure action is required;
- two core requirements conflict;
- product information that only the user can decide is missing, including unresolved D-01 or D-03;
- a security or legal risk cannot be judged safely;
- three consecutive valid iterations produce no measurable progress.

When blocked, record the exact acceptance ID, evidence, commands already attempted, smallest decision or authority needed, preserved rollback point, and the next safe action. A blocker never becomes a pass through wording changes.
