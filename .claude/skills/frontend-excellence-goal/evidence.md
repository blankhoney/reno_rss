# Frontend Excellence evidence ledger

| Field | Value |
|---|---|
| Status | In progress — Wave 0 browser foundation |
| Goal package prepared | 2026-07-21 |
| Execution branch | `feat/frontend-excellence` |
| Verified HEAD | Started at `dec47f67d9aaa0c7c87c5c3536e0a86feb15662c`; latest verified reader-web behavior is `591a8294` (`fix(reader-web): trap focus in modal layers`). |
| Runtime/environment | macOS arm64; Node 22; Playwright Chromium 149.0.7827.55 installed locally |
| Commit/push permission | Yes — user explicitly authorized multiple focused commits and pushes on 2026-07-21 |

Do not pre-mark rows as passed. Replace `Pending` only with an observed result or an explicit blocker.

## Baseline

| Check | Result | Evidence |
|---|---|---|
| Git status and HEAD | Observed | Started at `main@dec47f67`; execution moved to `feat/frontend-excellence`. `next dev` temporarily changed `next-env.d.ts`; stopping it and rerunning `npm run build` restored the file, so it is excluded from implementation scope. |
| Reader-web tests | Passed | `npm --prefix apps/reader-web test`: 171 passed, 0 failed, 0 skipped (2026-07-21). |
| Reader-web production build | Passed | `npm --prefix apps/reader-web run build`: compiled, TypeScript, and 4 routes succeeded (2026-07-21). |
| Browser runtime start | Passed | Playwright Chromium launched production standalone Reader Web through `npm run start:e2e`. |
| Service worker controlling page | Baseline passed | `e2e/service-worker.smoke.spec.ts`: `/sw.js` active after registration and `navigator.serviceWorker.controller` true on second local load. This does not yet prove cache/session policy. |
| Console errors | Pending | Smoke did not assert console output yet. |
| Horizontal overflow | Pending | Viewport matrix not yet implemented. |

## Audit hypotheses

| Context ID | Reproduced / refuted / blocked | Evidence and current paths |
|---|---|---|
| C-01 broad service-worker caching | Reproduced (source) | `public/sw.js` routes only `/api/articles*` network-first and all other same-origin GET to generic cache-first; `/api/auth/me` and `/api/jobs/{id}` are therefore unsafe. Real browser policy regression test is Wave 1. |
| C-02 mobile stacking conflict | Reproduced and mitigated | At 375×812, Chromium confirms `.mobileNavOverlay` has a higher computed layer than `.mobileBottomNav`; shared safe-area and semantic layer tokens shipped in `4f1d24a`. Drawer modal test also confirms the app and bottom nav are inert while open. Agent/selection/Toast coexistence remains Wave 2 work. |
| C-03 responsive mode collision | Reproduced and mitigated | Chromium at 899×900 confirms Focus mode no longer yields a `0px` workbench column after desktop-only Focus CSS in `4f1d24a`. 901px and dual-pane coverage remain pending. |
| C-04 keyboard scope | Reproduced and mitigated | `7445261` moves article shortcuts from `window` to a focusable article-list scope. Chromium confirms Enter on Sort opens its listbox without navigation, while focus on the list allows `j` to move the current article. |
| C-05 fragmented async truth | Pending | |
| C-06 return-context loss | Pending | |
| C-07 search races/partial failure | Pending | |
| C-08 job continuity | Pending | |
| C-09 annotation integrity | Pending | |
| C-10 continue-reading semantics | Pending | |
| C-11 contrast/token drift | Pending | |
| C-12 browser regression gap | Pending | |

## Acceptance ledger

| ID | Status | Implementation evidence | Verification evidence |
|---|---|---|---|
| FEX-01 | Passed | `sw.js` allowlists exact article-detail JSON and explicit shell/static assets; auth/jobs/annotations/export/Admin/search/list routes are not intercepted. | Node VM policy test plus Chromium job route sees two network responses. |
| FEX-02 | Passed | v2 owned cache names; activation removes obsolete `ai-reader-*` caches only; cache writes require successful JSON and use named cache matches. | Node VM tests cover failed/non-JSON exclusion and old-owned-cache deletion while preserving unrelated cache. |
| FEX-03 | Passed | `auth.ts` synchronizes the article-cache owner on session establishment and clears private cache on 401/logout; `sessionCache.ts` invalidates stale in-flight requests. | Chromium drives A article cache → real logout/login UI → offline B request; B receives 503 offline, never A payload. |
| FEX-04 | Passed | `/api/jobs/{id}` is outside the worker fetch allowlist. | Chromium worker-controlled second load receives queued then succeeded from two network job requests. |
| FEX-05 | Passed | Cached JSON remains on `getArticle()` → `articleFromApiDetail()` → `sanitizeArticleHtml()` path. | Node adapter test feeds script/`javascript:` JSON and asserts dangerous content is absent. |
| FEX-06 | In progress | `globals.css` defines documented semantic tokens for sticky UI, bottom navigation, popovers, Agent drawer, modal overlay, command palette, and toast. Opening Agent suppresses the selection toolbar while retaining its selection chip, avoiding competing action layers; mobile Toast moves above an expanded Agent. | Chromium at 375×812 confirms module drawer layers above bottom navigation; selected-text toolbar is constrained above navigation and disappears when Agent opens. At 390×844 and 768×1024, Toast is above Agent and Agent is above nav. Full simultaneous-layer matrix remains pending. |
| FEX-07 | In progress | Shared `--mobile-bottom-nav-offset` governs body, Focus reader, Agent and Toast; selection toolbar now uses the same offset at ≤900px; module drawer inerts app/background and locks scroll. | Chromium at 375×812 proves drawer is above bottom nav and background cannot be interacted with; a real mouse selection proves toolbar bounds stay within viewport and above nav, then yield to Agent with the selection chip preserved. At 390×844 and 768×1024, Agent and Toast remain separate from bottom navigation with no horizontal overflow. Per-control/per-viewport matrix remains pending. |
| FEX-08 | In progress | Focus-specific desktop grid rule is constrained to `min-width: 901px`; dual-pane CSS explicitly stacks its secondary content at ≤900px. | Chromium at 899×900 confirms nonzero workbench column and no horizontal overflow when dual-pane is enabled. At 901×900, after article-list load, Focus layout has no sidebar/mobile-nav duplicate and no horizontal overflow. Broader navigation accessibility matrix remains pending. |
| FEX-09 | Passed | `focusReaderLayout` explicitly contains primary article content and a notes/comparison secondary pane; desktop dual-pane uses readable primary/secondary columns while narrow layouts preserve the secondary pane after content. Scan / Focus / Keep remain persisted modes without introducing mode-specific navigation blockers. | Chromium at 1440×1000 confirms grid primary wider than secondary and no overlap; at 899×900 confirms block stacking after primary and no horizontal overflow. A 3-mode × 3-viewport matrix (375×812, 768×1024, 1440×1000) restores each mode, confirms article-list visibility/no overflow, enters focus reader, and finds article actions: 9/9 passed. |
| FEX-10 | Passed | Article triage keys are handled only by the focusable article-list root; interactive controls are excluded. | Chromium proves Sort button retains Enter behavior, article link Enter opens its reader route, Command Palette input and Agent textarea accept ordinary text, focused article list accepts `j`, and menus/dialogs retain their dedicated keyboard models. |
| FEX-11 | Passed | Module drawer and Command Palette use `useDismissableLayer` with initial focus, Tab containment, topmost Escape/outside arbitration, focus restoration, and inert background. Palette options expose active descendant IDs. Sort listbox and reader overflow use roving `tabIndex`, Arrow/Home/End, Enter/Space execution, `aria-controls`, and trigger restoration. | Chromium proves drawer focus stays inside, Escape restores hamburger; palette inerts workbench, focuses input, and Escape restores Sort. Sort proves Arrow/Home/End, Enter and Space selection and Escape restoration; reader overflow proves Arrow/Home/End and Escape restoration. |
| FEX-12 | Pending | | |
| FEX-13 | Pending | | |
| FEX-14 | Pending | | |
| FEX-15 | Pending | | |
| FEX-16 | Pending | | |
| FEX-17 | Pending | | |
| FEX-18 | Pending | | |
| FEX-19 | Pending | | |
| FEX-20 | Pending | | |
| FEX-21 | Pending | | |
| FEX-22 | Pending | | |
| FEX-23 | Pending | | |
| FEX-24 | Pending | | |
| FEX-25 | Pending | | |
| FEX-26 | Pending | | |
| FEX-27 | Pending | | |
| FEX-28 | Pending | | |
| FEX-29 | Pending | | |
| FEX-30 | Pending | | |
| FEX-31 | Pending | | |
| FEX-32 | Pending | | |

## Browser matrix

| Viewport | Theme | Motion | Flow/state | Result | Screenshot/log reference |
|---|---|---|---|---|---|
| 375×812 | light | normal | mobile navigation + Agent + Toast | Pending | |
| 390×844 | dark | reduced | Focus/Keep + selection | Pending | |
| 768×1024 | light | normal | search + article return | Pending | |
| 899×900 | dark | normal | responsive boundary | Pending | |
| 901×900 | light | reduced | responsive boundary | Pending | |
| 1440×1000 | light/dark | normal/reduced | dual pane + Admin/research | Pending | |

Add rows as needed for loading, empty, partial failure, full error, offline, queued, running, succeeded, failed, long content, and keyboard-only observations.

## Command results

Record the date, cwd, exact command, exit code, and meaningful output. Do not write “passed” without the result.

| Date | Command | Exit/result | Notes |
|---|---|---|---|
| 2026-07-21 | `npm --prefix apps/reader-web test` | 0 — 171 passed | First invocation from repository root was an `ENOENT` command-path error and did not run tests; corrected command is recorded here. |
| 2026-07-21 | `npm --prefix apps/reader-web run build` | 0 — compiled, TypeScript, 4 routes | Also restored the dev-generated `next-env.d.ts` reference. |
| 2026-07-21 | `npm --prefix apps/reader-web run test:e2e` | 0 — 1 Chromium test passed | Initial smoke verifies standalone public/static copy and second-load Service Worker control. |
| 2026-07-21 | `npm test && npm run build && npm run test:e2e && git diff --check` (cwd `apps/reader-web`) | 0 — 176 Node tests, build passed, 3 Chromium tests passed | Wave 1 full gate: allowlist/lifecycle, job freshness, A→B offline isolation, sanitizer path. |
| 2026-07-21 | `npm test && npm run build && npm run test:e2e && git diff --check` (cwd `apps/reader-web`) | 0 — 178 Node tests, production build passed, 8 Chromium tests passed | Wave 2 modal slice: drawer/palette focus trap, inert background, Escape top-layer dismissal and trigger restoration; prior PWA/layer/keyboard tests also passed. Verified before commit `591a829`. |
| 2026-07-21 | `npm test && npm run build && npm run test:e2e && git diff --check` (cwd `apps/reader-web`) | 0 — 178 Node tests, production build passed, 10 Chromium tests passed | Wave 2 menu slice: Sort listbox and reader overflow roving keyboard operation, Enter/Space selection, Escape and trigger restoration. |
| 2026-07-21 | `npm test` (captured exit), `npm run build`, `npm run test:e2e`, `git diff --check` (cwd `apps/reader-web`) | all 0 — 178 Node tests, production build passed, 12 Chromium tests passed | Wave 2 dual-pane slice: explicit primary/secondary structure; 1440px desktop columns and 899px stack/no-overflow proof. The harness truncated the combined TAP stream and reported a nonzero wrapper result twice; captured raw `npm test` exit code was 0, so commands are recorded independently. |
| 2026-07-21 | `npm test` (captured exit), `npm run build`, `npm run test:e2e`, `git diff --check` (cwd `apps/reader-web`) | all 0 — 178 Node tests, production build passed, 13 Chromium tests passed | Wave 2 mobile selection slice: real mouse selection at 375px, toolbar width/safe-area geometry, and Agent handoff retaining the selected-text chip. |
| 2026-07-21 | `npm test` (captured exit), `npm run build`, `npm run test:e2e`, `git diff --check` (cwd `apps/reader-web`) | all 0 — 178 Node tests, production build passed, 16 Chromium tests passed | Wave 2 responsive layer slice: 390/768 Agent+Toast+bottom-nav geometry and no overflow; 901px Focus desktop transition after real list load. |
| 2026-07-21 | `npm test` (captured exit), `npm run build`, `npm run test:e2e`, `git diff --check` (cwd `apps/reader-web`) | all 0 — 178 Node tests, production build passed, 25 Chromium tests passed | Wave 2 mode matrix: Scan/Focus/Keep restored and navigated at 375/768/1440; dual-pane proof retained at 899/1440. |
| 2026-07-21 | `npm test` (captured exit), `npm run build`, `npm run test:e2e`, `git diff --check` (cwd `apps/reader-web`) | all 0 — 178 Node tests, production build passed, 26 Chromium tests passed | Wave 2 native keyboard slice: links, button/listbox/menu, modal drawer, palette input, and Agent textarea preserve their expected keyboard behavior. |

## API/OpenAPI gate

Only fill this section if API behavior or shape changed.

| Check | Result |
|---|---|
| API pytest | Not applicable / Pending |
| API Ruff | Not applicable / Pending |
| OpenAPI regenerated | Not applicable / Pending |
| Generated TypeScript regenerated | Not applicable / Pending |
| Regeneration drift check | Not applicable / Pending |

## Decisions and deviations

| Decision | Reason | Approval/evidence |
|---|---|---|
| Indigo is the primary action accent unless root `GOAL.md` is explicitly changed | Subordinate goal must comply with parent Goal | Root `GOAL.md` §5 |
| Add Playwright as a development dependency | User explicitly selected Playwright after the local machine lacked a browser driver; Node tests cannot prove Service Worker control, focus, or fixed-layer geometry | User selection during approved Goal plan, 2026-07-21; official Playwright `webServer`/Chromium guidance consulted |
| Use standalone E2E server with copied `public` and `.next/static` | Matches the existing Dockerfile; direct `.next/standalone/server.js` did not serve `/sw.js`, so `navigator.serviceWorker.ready` timed out | Reproduced then fixed by `e2e/service-worker.smoke.spec.ts` |

Record any acceptance interpretation, scope reduction, dependency addition, or root-Goal conflict here. A scope reduction does not silently waive a MUST criterion.

## Environment limits and blockers

- None recorded yet.

## Final review

- [ ] Every FEX row has observed evidence.
- [ ] Every applicable command passed on the verified HEAD.
- [ ] Browser console is clean for the tested critical flows.
- [ ] No required observation is represented by an unverified assumption.
- [ ] `docs/learning-notes.md` is current.
- [ ] Final diff contains no unrelated edits or secrets.
- [ ] Commit/push/deploy actions match explicit user permission.

## Handoff if incomplete

State the first incomplete acceptance ID, exact blocker, files/commands already tried, current dirty files, and the smallest next action. Never convert a blocker into a completion claim.
