# Frontend audit context

This file is a prepared baseline, not a substitute for reproduction. Line numbers describe `main@dec47f67` and may move. At execution time, verify every claim against the current HEAD before editing.

## Current product surface

The App Router has two physical pages:

- `/` dispatches Daily Intelligence, article workbench, review, search, product panels, and Admin through the `module` query parameter: `apps/reader-web/src/app/page.tsx`.
- `/read/[id]` hosts the focused reader and return context: `apps/reader-web/src/app/read/[id]/page.tsx`.

Primary user journeys already present:

- Daily Intelligence and source/cluster radar.
- Article Scan workbench with sorting, pagination, Top10, keyboard triage, and saved/project state.
- Focus reader with original/translation views, scoring, feedback, annotations, research Agent, related content, and dual-pane modes.
- Keep flows through review, search, saved searches, projects, and export.
- Research jobs and Admin pipeline/cost controls.
- Mobile drawer, bottom navigation, command palette, themes, density, reduced motion, and PWA registration.

Do not spend a new delivery wave recreating those surfaces.

## Current design and architecture facts

- The live design system is custom CSS in `apps/reader-web/src/app/globals.css`; there is no Tailwind or shadcn runtime.
- The visual DNA is warm paper, editorial typography, and a warm dark theme.
- Root `GOAL.md` specifies a single indigo action accent, while the current token is terracotta (`--accent: #b4541f`). Treat this as a contract conflict to resolve deliberately, not an invitation to create two action palettes.
- Browser data flows through `apps/reader-web/src/lib/api/*` to same-origin FastAPI `/api/*`.
- Article HTML is sanitized in `src/lib/articles/service.ts` before render.
- Existing stale-request guards, article-change events, URL state, and saved → project action paths are protected behavior, not cleanup opportunities.

## Confirmed high-risk evidence

### C-01 — broad service-worker caching

`apps/reader-web/public/sw.js` special-cases only `/api/articles*`; every other same-origin GET falls through to `cacheFirstShell()`. That function stores responses without checking `response.ok`, and `activate` does not remove old cache versions.

Reproduce consequences before fixing:

- auth/session freshness after logout or account change;
- `/api/jobs/{id}` progression from queued/running to terminal;
- private annotation/search/export/Admin data retention;
- stale briefs, themes, clusters, feeds, recommendations, and review data;
- behavior after a cache-version change.

### C-02 — mobile stacking conflict

At the design baseline:

- `--z-drawer` is 20;
- overlays/mobile bottom navigation use 40;
- the mobile Agent drawer sits at `bottom: 10px`;
- the bottom navigation is fixed at the bottom and adds safe-area padding.

Test drawer, Agent, Toast, selection UI, and bottom navigation together at 375×812 and 390×844. Do not “fix” this by assigning arbitrary larger numbers without a documented layer contract.

### C-03 — responsive mode collision

`html[data-reader-mode="focus"] .workbench` defines `grid-template-columns: 0 minmax(0, 1fr)` after the mobile workbench rules. Dual pane applies a two-column grid to `.focusReader` without a mobile fallback. Reproduce Focus/Keep/dual-pane behavior at 899/901 and narrow-phone widths.

### C-04 — keyboard scope

Article triage listens at `window` level. Current editable-target filtering excludes text-editing controls but may not protect focused buttons, links, menu items, and dialogs. Verify Enter/Space and j/k/r/s/p from every interactive surface before changing the handler.

### C-05 — fragmented async truth

Known candidates include:

- Daily Intelligence requests where non-brief failures can appear as empty data;
- Rules and saved-search views where an empty array can also mean “not loaded”;
- Pipeline health that can remain visually “loading” after a failed request;
- search that discards both result sets when either source fails;
- reader annotation load failure that can appear as no annotations.

Build a shared state vocabulary only after mapping current consumers; do not force every component into a speculative abstraction.

### C-06 — return-context loss

The read route currently preserves module, sort, language, and article identity, but list page/cursor-equivalent state, search filter/query, active index, and scroll position need verification. Reproduce read-and-return from a later page and from search before deciding whether URL state, history state, or session state is the smallest fix.

### C-07 — search races and partial failure

Unified search combines article and annotation requests, lacks an explicit stale-response/abort contract, and does not fully synchronize submitted state to the URL. Verify fast A→B queries, one-source failure, refresh/share, and article-return behavior.

### C-08 — research/Admin job continuity

Research job identity is primarily component state. Refreshing or navigating away can lose polling context. Admin completion may not refresh every dependent card. Verify current API capabilities before adding storage or new endpoints.

### C-09 — annotation interaction integrity

Selection positioning is tied mainly to pointer/touch completion; controls inside the selection UI may collapse the browser selection. Existing notes need honest display and failure handling. Reproduce keyboard selection, duplicate quote text, cross-element selection, and content refresh before choosing an anchoring strategy.

### C-10 — continue-reading semantics

The API exposes `read_progress`, while current frontend adaptation and labels may conflate saved/read-later/candidate state. Decide from existing contracts whether to expose real progress or correct the wording; do not invent a client-only source of truth.

### C-11 — contrast and token drift

The light muted/warning colors are candidates for sub-AA normal-text contrast. CSS also contains token drift such as `--panel-2` versus `--panel2`, undeclared `--mono`, and local highlight colors. Measure before changing; correct at token level where possible.

### C-12 — regression gap

The existing Node test glob runs `src/**/*.test.ts`. It does not by itself catch service-worker lifecycle, fixed-layer occlusion, focus containment, return scroll, or responsive overflow. Keep pure tests, but add the smallest real-browser coverage needed for these failure classes.

## Already completed — preserve, do not rebuild

- 2a warm-editorial two-column workbench and ScoreRing.
- Stale-request sequence guards in article/workbench loading.
- Silent refresh after article writes.
- Client navigation and session cache.
- Command palette and article triage shortcuts.
- Mobile module drawer and bottom navigation.
- Reader/list skeletons and explicit translation states.
- Toast motion and reduced-motion-aware Agent typewriter.
- Daily Intelligence, review, clusters, themes, research, search, rules, interests, craft controls, and export surfaces.

## Documentation caveats

- `docs/spec/FRONTEND.md` is historical and still describes Tailwind/shadcn aspirations; it is not the implementation source of truth.
- `docs/goal-completion-evidence.md` records the 2026-07-18 completion claim, but this Goal intentionally re-tests fragile browser behavior rather than treating that evidence as perpetual.
- The root Goal's current-state gap table contains stale statements for some features. Do not remove working functionality because a narrative table says it is absent.
- The repository ignores new files under `docs/`; this tracked Skill package lives under `.claude/skills/` so it can be shared.

## Required first observation set

Before product edits, capture and record:

1. Current commit, branch, and dirty files.
2. `npm test` and `npm run build` baseline.
3. Light/dark screenshots at 375×812, 390×844, 768×1024, 899×900, 901×900, and 1440×1000.
4. Scan, Focus, Keep/dual-pane, search, research, and Admin states.
5. Loading, empty, error, partial error, offline, queued/running/succeeded/failed where reproducible.
6. Keyboard-only navigation and modal focus behavior.
7. Service-worker-controlled second load, logout/session change, and job polling.
8. Browser console errors and horizontal overflow.

Record environmental limits honestly. Lack of Docker, credentials, or a safe mock backend is a blocker or an unrun check, never a pass.
