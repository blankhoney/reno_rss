# Execution plan

Execute waves in order. A wave may be split into smaller focused tasks, but do not begin a dependent wave until the prior wave's acceptance evidence is credible. Re-run affected earlier checks after later shared-CSS or navigation changes.

## Wave 0 — baseline, decision log, and reproduction

### Purpose

Establish current behavior so the work fixes observed problems rather than implementing the audit report by assumption.

### Actions

- Check branch, HEAD, working-tree status, available runtime, and whether the current page is controlled by a service worker.
- Run the existing reader-web tests and production build.
- Launch the real app through the project's run/verification workflow using a safe local or mock-backed setup.
- Capture the required viewport/theme/motion matrix from `context.md`.
- Reproduce or refute C-01 through C-12 and write the result into `evidence.md`.
- Record the design decision: root `GOAL.md` indigo action accent is authoritative unless the maintainer explicitly changes it.
- Identify the smallest files and tests for Wave 1; do not pre-author a framework-wide refactor.

### Exit gate

- Baseline commands and browser observations are recorded.
- Each P0 claim has a reproduction or a documented refutation.
- No unexplained dirty file exists.

## Wave 1 — private cache and PWA correctness

### Purpose

Make offline support safe before polishing presentation.

### Expected focus

- `apps/reader-web/public/sw.js`
- service-worker registration/session/logout integration
- focused PWA/cache tests
- browser proof under service-worker control

### Rules

- Use an explicit cache allowlist, not a growing denylist of private endpoints.
- Cache only successful responses with an intentional strategy.
- Version and remove obsolete caches.
- Define logout/session-change cleanup behavior.
- Preserve sanitization on any offline article path.
- Do not add offline mutation queues or a second local database.

### Exit gate

FEX-01 through FEX-05 pass, including a real queued→terminal polling observation while the service worker controls the page.

## Wave 2 — mobile layers, responsive modes, and keyboard access

### Purpose

Make existing navigation and reading modes usable without overlap, click-through, or keyboard theft.

### Expected focus

- layer/z-index and safe-area tokens
- mobile drawer, bottom navigation, Agent drawer, Toast, selection UI
- Focus/Keep/dual-pane responsive behavior
- shortcut scope
- dismissable/modal/menu primitives only where reuse is proven
- light/dark contrast tokens

### Rules

- Document a layer contract before changing z-index values.
- Do not hide conflicts with arbitrary `z-index: 9999`.
- Mobile dual pane must intentionally degrade to one pane, tabs, or a sheet.
- Native focused-control behavior wins over global shortcuts.
- All new motion has a reduced-motion equivalent.

### Exit gate

FEX-06 through FEX-11 pass at all required viewport and interaction states.

## Wave 3 — truthful async states and research continuity

### Purpose

Ensure navigation, search, research, and Admin display real state and survive ordinary user movement.

### Expected focus

- article return context
- search URL/race/partial failure
- research job recovery
- Admin refresh and per-card status
- Daily Intelligence and product-panel async states
- continue-reading/read-later semantics

### Rules

- Preserve server sorting/cursor contracts.
- Prefer URL/history/session state over a new global state library.
- Do not label errors as empty results.
- Do not claim a job is still loading after its request failed.
- Do not add a general job platform; solve existing research/Admin flows.

### Exit gate

FEX-12 through FEX-18 pass with refresh, back/forward, and partial-failure observations.

## Wave 4 — private knowledge integrity

### Purpose

Make existing highlight/note flows robust enough to trust.

### Expected focus

- keyboard, mouse, and touch selection
- selection preservation while editing controls
- existing annotation visibility and error handling
- smallest stable quote/paragraph anchoring improvement justified by evidence
- reader → review → search continuity

### Rules

- Do not bypass FastAPI with local-only durable state.
- Any new API capability must be per-user, tested, and reflected in OpenAPI/generated TypeScript.
- Preserve sanitization when injecting highlight marks.
- Repeated text and refreshed article content must not silently highlight the wrong passage.

### Exit gate

FEX-19 through FEX-22 pass, or a missing backend capability is explicitly approved as a separate blocker. An unapproved blocker means the Goal remains incomplete.

## Wave 5 — design contract and page-level polish

### Purpose

Consolidate the visual language after correctness and state contracts are stable.

### Expected focus

- warm-paper + indigo action token contract
- AA light/dark colors
- typography, spacing, density, focus rings, skeleton alignment
- shared async/modal/form/surface primitives only where repeated
- route-level loading/error/not-found boundaries where useful
- verified dead CSS/token cleanup

### Rules

- No Tailwind/shadcn or second component library.
- Do not change brand, layout architecture, and interaction architecture simultaneously.
- Do not remove CSS based only on grep; verify production rendering.
- Publication-grade means readable and calm, not animation-heavy.

### Exit gate

FEX-23 through FEX-27 pass, and before/after screenshots show one coherent system rather than isolated restyling.

## Wave 6 — regression net and final evidence

### Purpose

Prove the result and leave maintainable protection.

### Actions

- Add or finish the smallest browser regression suite that exercises the critical flows.
- Run all required commands from `acceptance.md`.
- Re-run the viewport/theme/motion and service-worker matrices.
- Check browser console, horizontal overflow, focus order, and back/forward behavior.
- Update `docs/learning-notes.md` and complete every applicable row in `evidence.md`.
- Run `git diff --check` and review the final diff for unrelated changes.
- Use the project verification skill to drive affected runtime flows.

### Exit gate

FEX-28 through FEX-32 pass. Every MUST row is complete, no unrecorded exception remains, and the transcript contains enough evidence for `/goal` evaluation.

## Verification cadence

After each focused task:

1. Run the smallest relevant test.
2. Exercise the changed browser behavior.
3. Run broader reader-web tests before ending the wave.
4. Record actual evidence.

At the final gate:

```bash
cd apps/reader-web
npm test
npm run build

cd ../..
git diff --check
```

If API code or API shape changes, also run the API pytest/Ruff gates and regenerate both `apps/api/openapi.json` and `apps/reader-web/src/lib/api/generated/schema.ts`, proving regeneration has no unexplained drift.

## Stop and ask conditions

Stop for a genuine user decision when the next step would:

- change the root product Goal rather than comply with it;
- add a runtime dependency or browser-test framework with material maintenance cost;
- require a database migration or broad API redesign;
- use real LLM credits, production data, secrets, external publication, or deployment;
- delete user-authored content or overwrite contradictory uncommitted work;
- require commit/push permission that was not explicitly provided.

Otherwise choose the simplest reversible implementation and continue.
