# AI Reader Frontend Excellence Goal

| Field | Value |
|---|---|
| Status | Prepared; not started |
| Prepared | 2026-07-21 |
| Design baseline | `main@dec47f67` (must be re-checked at launch) |
| Parent | Repository root `GOAL.md` |
| Primary surface | `apps/reader-web` |
| Goal class | Subordinate execution goal, not a second product Goal |

## One-sentence end state

Turn the existing 2a warm-editorial frontend from a broad feature surface into a **trustworthy daily research workspace**: across 375–1440px, keyboard-only use, light/dark themes, failure/recovery, offline/session transitions, and long-running jobs, the Scan → Focus → Keep → Research → Admin journey loses no private data, hides no failure, traps no user, and preserves context with publication-grade visual craft.

## Why this is the next goal

The project already has Daily Intelligence, Scan/Focus/Keep, command navigation, mobile navigation, private annotations, research jobs, Admin controls, and PWA support. The next quality ceiling is not another module. It is making the existing system correct and coherent under the conditions where real products fail: stale caches, account changes, narrow screens, overlapping fixed layers, keyboard focus, partial API failures, navigation away and back, refresh during a job, and ambiguous loading/empty/error states.

## Product promises

A completed implementation must make these promises true:

1. **Private means private.** Service-worker and browser caches never expose one session's private API data to another session, never freeze job polling, and never bypass sanitization.
2. **State tells the truth.** Loading, empty, partial failure, complete failure, stale, offline, queued, running, succeeded, and failed are distinguishable where they matter.
3. **Research continuity survives navigation.** Returning from an article, refreshing a research job, revisiting search, or changing viewport does not silently discard the user's place or work.
4. **Mobile and keyboard are first-class.** No fixed layer obscures another; no global shortcut steals a focused control; modal focus and Escape behavior are predictable.
5. **Knowledge capture is dependable.** Mouse, touch, and keyboard selection paths are usable; existing annotations are visible; failures are not misrepresented as empty data.
6. **The design contract is singular.** The app keeps the warm-paper 2a DNA, uses the root Goal's indigo action accent unless the maintainer explicitly changes that Goal, meets AA contrast, and does not introduce a second component-library aesthetic.
7. **Completion is observable.** Automated checks, real browser paths, viewport/theme/motion matrices, and known environment limits are recorded in `evidence.md`.

## Scope

### P0 — correctness and privacy

- Replace the service worker's broad same-origin GET cache behavior with an explicit allowlist and lifecycle policy.
- Prevent cached auth, job, export, annotation, search, review, Admin, brief, cluster, theme, feed, or other private/dynamic responses from becoming stale or crossing sessions.
- Verify cache cleanup/versioning and logout/session-change behavior.
- Preserve article HTML sanitization for online and offline paths.

### P0 — interaction geometry and input correctness

- Resolve mobile bottom navigation, navigation drawer, Agent drawer, selection UI, Toast, sticky bars, and safe-area stacking.
- Make Scan/Focus/Keep and dual-pane behavior intentional at 375, 390, 768, 899, 901, and 1440px.
- Scope article shortcuts so focused links, buttons, inputs, dialogs, menus, and editable surfaces retain native keyboard behavior.
- Establish correct modal focus containment, focus restoration, Escape behavior, ARIA state, and background inertness.

### P1 — continuity and honest async states

- Preserve article-list/search context across read-and-return flows: query, filter, sort, page/cursor-equivalent state, active item, and scroll/return target where feasible.
- Make unified search race-safe, URL-addressable, and partially usable when one data source fails.
- Make research/Admin jobs recoverable after refresh or navigation and ensure terminal completion refreshes dependent cards.
- Give every primary view a deliberate loading, empty, error, retry, and partial-failure contract.
- Correct misleading “continue reading” or “read later” semantics by using actual progress or honest labeling.

### P1 — private knowledge integrity

- Make selection and annotation creation usable by mouse, touch, and keyboard.
- Prevent annotation controls from collapsing the selection they are editing.
- Show existing annotations and annotation-load failures honestly in the reader.
- Use the smallest durable anchoring improvement justified by reproduced failures; do not invent a parallel client-only knowledge database.
- If an essential UI requires a missing API capability, add only the minimal per-user FastAPI/repository contract with tests and generated-schema synchronization.

### P2 — design-system consolidation and regression proof

- Align the interactive accent contract with root `GOAL.md`: warm paper remains the reading foundation; indigo is the primary action accent unless the maintainer explicitly approves a Goal change.
- Correct light/dark contrast at token level and cover it with deterministic checks where practical.
- Consolidate only proven shared primitives such as async state, dismissable/modal layers, buttons, fields, or surfaces; avoid broad rewrites.
- Remove dead or drifting CSS only with production-reference and browser evidence.
- Add the smallest browser-level regression suite capable of catching cache, navigation, keyboard, overlay, and responsive failures that Node source-contract tests cannot.
- Add App Router error/not-found/loading boundaries only where they provide route-level recovery without duplicating component state.

## Hard constraints

- Root `GOAL.md`, `AGENTS.md`, and current API contracts outrank this package.
- Miniflux remains the feed/entry source of truth.
- Browser code never connects directly to Miniflux or PostgreSQL.
- All untrusted article HTML passes through `sanitizeArticleHtml()` before rendering, including offline data.
- Agent output remains `<think>`-stripped, Markdown-only, and raw-HTML-free.
- Saved → project semantics remain enforced through FastAPI.
- Production stays fail-closed; staging anonymous-demo behavior and Admin protection stay unchanged.
- No real secrets, user databases, API keys, or production data enter Git or evidence files.
- No unbounded LLM-cost path; automated verification uses mock providers.
- No Tailwind/shadcn migration, framework rewrite, global state rewrite, or unrelated backend redesign.
- No commit, push, PR, merge, deployment, or external publication unless the user explicitly authorizes it at invocation time.

## Non-goals

- Adding more sidebar modules merely to increase feature count.
- Replacing Next.js, React, the App Router, or the same-origin FastAPI adapter architecture.
- Turning the product into a generic notebook, chat app, social feed, or offline-first database.
- Replacing PostgreSQL search or introducing a new search engine without measured evidence.
- Redesigning recommendation algorithms, worker scheduling, authentication, or infrastructure unless required to preserve an existing frontend contract.
- A decorative re-skin without correctness, accessibility, continuity, and evidence improvements.

## Definition of done

The Goal is complete only when all MUST criteria in `acceptance.md` are demonstrated on the current implementation, every required automated command passes, the browser matrix is observed without unrecorded exceptions, `docs/learning-notes.md` and `evidence.md` are current, and no security/architecture invariant has regressed.
