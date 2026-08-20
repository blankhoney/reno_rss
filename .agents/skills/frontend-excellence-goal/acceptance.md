# Acceptance contract

Every item below is a **MUST** unless explicitly labeled SHOULD. Evidence must identify the current commit, command/output or browser observation, and any environmental limitation.

## A. Private cache and PWA correctness

- **FEX-01 — Explicit cache boundary.** The service worker caches only an explicit set of shell/static resources and deliberately approved offline article responses. Dynamic/private API classes such as auth, jobs, annotations, export, Admin, search, review, briefs, clusters, themes, feeds, and recommendations are never handled by a generic cache-first fallback.
- **FEX-02 — Response and lifecycle safety.** Only successful intended responses enter caches; old cache versions are removed during activation; cache naming and ownership are documented and tested.
- **FEX-03 — Session isolation.** After logout or a simulated account/session change, the next session cannot receive the prior session's auth, annotation, search, export, article, or Admin response from CacheStorage.
- **FEX-04 — Job freshness.** With a service worker controlling the page, an existing job can be observed moving from queued/running to succeeded/failed without a cached status freezing polling.
- **FEX-05 — Offline sanitization.** Any offline article payload still passes through the existing article adapter and `sanitizeArticleHtml()` before rendering; no raw cached HTML path is introduced.

## B. Mobile, responsive modes, and keyboard access

- **FEX-06 — Layer contract.** Drawer, overlay, command palette, Agent drawer, bottom navigation, selection UI, Toast, and sticky bars have a documented layer order with no dependence on accidental DOM order.
- **FEX-07 — Mobile geometry.** At 375×812, 390×844, and 768×1024, opening the module drawer, Agent, selection UI, and Toast does not cause obscured controls, click-through, unreachable content, or unhandled safe-area overlap.
- **FEX-08 — Breakpoint continuity.** At 899px and 901px, navigation and workbench layout change intentionally without duplicate controls, missing controls, or horizontal overflow.
- **FEX-09 — Scan/Focus/Keep.** At phone, tablet, and 1440px desktop widths, each reader mode remains navigable. Dual pane uses a readable desktop width and intentionally falls back to a single-pane/tab/sheet experience on narrow screens.
- **FEX-10 — Keyboard scope.** Focused buttons, links, menu items, form controls, dialogs, and editable content retain native Enter/Space/text behavior. Article j/k/r/s/p shortcuts only apply in a documented article-list scope.
- **FEX-11 — Modal and menu access.** Modal surfaces contain focus, background content is inert where appropriate, Escape closes, focus returns to the trigger, and menus/listboxes support the expected arrow-key model and exposed active state.

## C. Truthful states and continuity

- **FEX-12 — Read-and-return.** Entering an article from a later article-list page and returning restores the correct module, sort, page/cursor-equivalent position, active card, and visible return target without resetting silently to page one.
- **FEX-13 — Search continuity.** Submitted search state is reflected in a reloadable/shareable URL. A fast A→B query cannot render stale A results after B, and browser back/forward restores the visible query/filter state.
- **FEX-14 — Search partial failure.** Article results remain usable when annotation search fails and vice versa; the failed source is identified without discarding successful results.
- **FEX-15 — Research recovery.** A running research job survives refresh or navigation away/back through an existing durable identifier or the smallest justified persistence mechanism; terminal state and result remain reachable.
- **FEX-16 — Admin truth.** Pipeline/usage/batch cards have independent loading/error/retry contracts. A failed request never displays permanent “loading,” and terminal operations refresh affected cards.
- **FEX-17 — Primary-view state matrix.** Daily Intelligence, Review, Clusters, Themes, Rules, Saved Searches, Research, Search, Interest, Export, article workbench, reader, and Admin each distinguish the states they can actually enter: loading, empty, error, retry, partial failure, success, and offline/stale where applicable.
- **FEX-18 — Honest reading labels.** “Continue reading,” “read later,” saved/candidate, and project labels match the data contract. Real `read_progress` is used where the UI promises progress, or the promise is renamed so it is not misleading.

## D. Private knowledge integrity

- **FEX-19 — Multi-input selection.** Mouse, touch, and keyboard text selection can enter the intended highlight/note flow without requiring a pointer-only event.
- **FEX-20 — Stable editor interaction.** Choosing color, entering tags/notes, or tabbing through selection controls does not collapse or silently lose the pending selection.
- **FEX-21 — Existing-data truth.** Existing annotations are visible from the reader/notes surface, and an annotation-load failure is shown as an error/retry state rather than an empty collection.
- **FEX-22 — Anchor integrity.** Repeated quote text, selection across inline markup, and article-content refresh do not silently apply a highlight to the wrong passage. The chosen anchor strategy remains user-isolated and sanitization-safe.

## E. Design contract and page polish

- **FEX-23 — Single visual contract.** Warm paper and the existing editorial typography remain the reading foundation. Interactive accent tokens comply with root `GOAL.md`'s indigo direction unless a separately approved root-Goal change says otherwise; terracotta is not left as a competing primary action color.
- **FEX-24 — AA contrast.** Required normal text reaches WCAG AA 4.5:1 and large text 3:1 in light and dark themes. Disabled/decorative exceptions do not carry required information.
- **FEX-25 — Unified async language.** Skeleton, empty, error, retry, stale/offline, and success presentation uses a coherent visual and copy system without forcing unrelated components into one oversized abstraction.
- **FEX-26 — Route recovery.** App Router loading/error/not-found boundaries exist where route-level failure currently strands the user, and they do not duplicate or conflict with component-level business states.
- **FEX-27 — CSS integrity.** Undefined/drifting tokens and confirmed dead CSS are corrected without unrelated reformatting. No Tailwind/shadcn or second component-library aesthetic is introduced.

## F. Regression proof and delivery hygiene

- **FEX-28 — Reader-web tests.** From `apps/reader-web`, `npm test` exits 0 and all newly added tests are included by the actual `src/**/*.test.ts` discovery rule, or the rule is deliberately updated and proven if a different extension is necessary.
- **FEX-29 — Production build.** From `apps/reader-web`, `npm run build` exits 0 with TypeScript and production routes built.
- **FEX-30 — Browser regression.** Automated or repeatable browser proof covers at minimum: service-worker second load/session transition; queued→terminal job; later-page article return; A→B search race/partial failure; 375px drawer+bottom-nav+Agent; keyboard command/menu/article triage; annotation selection; light/dark and reduced motion.
- **FEX-31 — Repository hygiene.** `git diff --check` exits 0; the final diff contains no secrets, generated runtime output, unrelated formatting, silent dependency additions, or unauthorized deployment/commit artifacts.
- **FEX-32 — Evidence and learning.** `evidence.md` maps every acceptance ID to actual proof or an explicit blocker; `docs/learning-notes.md` explains durable behavior/process knowledge in the project's teaching format.

## Required browser matrix

| Dimension | Values |
|---|---|
| Viewport | 375×812, 390×844, 768×1024, 899×900, 901×900, 1440×1000 |
| Theme | light, dark |
| Motion | normal, `prefers-reduced-motion` |
| Data state | loading, empty, partial failure, full error, success; offline/stale where applicable |
| Content stress | long title, long username, long Agent answer, long article, code block, wide image/table |
| Input | mouse, touch-equivalent, keyboard-only |
| History | reload, back, forward, article return, leave/resume job |

A representative pairwise matrix is acceptable where testing every Cartesian combination would add no information, but every listed value and every P0 interaction must appear in evidence.

## Conditional API gate

If API behavior or schema changes:

```bash
cd apps/api
uv run --isolated --with-editable . --extra dev python -m pytest tests -q
uv run --isolated --with-editable . --extra dev ruff check .
uv run --isolated --with-editable . --extra dev python -m app.export_openapi --out openapi.json

cd ../..
npx --yes openapi-typescript@7.13.0 apps/api/openapi.json -o apps/reader-web/src/lib/api/generated/schema.ts
git diff --exit-code -- apps/api/openapi.json apps/reader-web/src/lib/api/generated/schema.ts
```

Do not run or claim this gate when no API surface changed. If run, record actual results.

## Completion rule

No aggregate test count, screenshot set, or visual impression can waive a failed MUST item. If environment access prevents a required browser/security observation, mark it blocked and leave the Goal incomplete with the exact command, account, service, or decision needed next.
