---
name: reader-web-audit
description: Audit this repository's complete Reader Web experience with evidence-backed browser, visual, state-truth, accessibility, responsive, keyboard, touch-equivalent, and privacy checks. Use whenever the user asks to inspect, optimize, redesign, screenshot, record, review, or improve Reader Web UX/UI, reading experience, visual quality, responsive behavior, accessibility, or Playwright evidence. This is a manually invoked, read-only-by-default project skill; it does not authorize product edits, deployment, production access, database writes, secrets, or real-provider spend.
disable-model-invocation: true
argument-hint: "[baseline|page|flow|diff] [target]"
---

# Reader Web evidence audit

Use this skill to turn visual or UX opinions into reproducible findings. The audit should explain what was observed, why it matters to the research workflow, which existing contract it touches, and what the smallest verifiable next action is.

## 1. Load current authority

Read these live files in order before forming conclusions:

1. `AGENTS.md`
2. `GOAL.md`
3. `PLANS.md`
4. `CLAUDE.md`
5. Relevant current source/tests

Treat historical files under `.claude/skills/frontend-excellence-goal/`, `docs/superpowers/`, and old evidence ledgers as context, not authority. If they conflict with the root files or current code, report the drift instead of following the historical snapshot.

Preserve user-owned worktree changes. In particular, do not edit, stage, clean, or overwrite a modified `GOAL.md` unless the user explicitly authorizes that exact change.

## 2. Default operating mode

The default is **read-only audit**:

- Inspect source, tests, deterministic fixtures, screenshots, traces, and local browser behavior.
- Use the existing fixture-backed Playwright server for browser evidence.
- Record an unrun check as `NOT RUN`, not PASS.
- Label missing evidence as `NEEDS_BASELINE` or `IN_PROGRESS`.
- Do not edit product files until the user separately requests implementation or has approved an implementation plan.

Never use this skill as permission to:

- read or print `.env`, cookies, tokens, SSH keys, provider keys, authentication headers, or secret stores;
- connect to or mutate production/staging services;
- deploy, restart, rollback, open ports, alter DNS, or change Caddy/Authelia;
- write to a database or run migrations;
- call a real LLM provider or consume paid model budget;
- capture real user articles, annotations, prompts, or account data in screenshots/videos.

When a later approved implementation requires one of these risk surfaces, explain it separately and obtain the required explicit authorization.

## 3. Choose the audit scope

Interpret `$ARGUMENTS`:

- `baseline`: audit representative Reader Web surfaces and establish fixture-only evidence.
- `page <route/component>`: inspect one page or component deeply.
- `flow <name>`: drive one user flow across states and navigation.
- `diff`: audit only the current working diff and affected flows.
- no arguments: choose the smallest scope that answers the user's request; do not silently expand to a whole-product redesign.

Prefer one acceptance slice at a time. Current root `GOAL.md` priority always wins over a broad visual wish list.

## 4. Build an evidence map before judging design

For the selected scope, identify:

- Route and owning components.
- API adapters and server-owned state.
- Fixture controls and relevant Playwright tests.
- Existing CSS tokens/primitives and reusable interaction utilities.
- Security/privacy invariants that the surface depends on.
- Relevant `GOAL.md` acceptance rows, normally A-02, A-04, A-05, A-06, A-07, A-09, A-13, and A-15.

Read `references/audit-checklist.md` for the detailed matrix. Reuse existing seams instead of proposing new infrastructure when the repository already has an appropriate helper.

## 5. Observe the real interface safely

Use `/run` or the existing fixture-backed Playwright setup when browser observation is needed. Prefer deterministic local data and representative pairwise coverage over a huge Cartesian matrix.

Capture, as relevant:

- desktop and mobile;
- light and dark themes;
- keyboard and pointer; touch-equivalent only where native touch cannot be proven;
- loading, confirmed empty, partial success, error, retrying, recovered success;
- long title, long article, missing summary, narrow viewport, sticky-layer stress;
- article entry, Back, refresh, and restored URL/list context;
- reduced motion and visible focus.

A screenshot proves appearance at one moment. Pair it with DOM, URL, network, accessibility, or state assertions when making behavioral claims. A programmatically created text range plus `tap()` proves touch-equivalent saving, not native touch text selection.

## 6. Screenshot, trace, and video rules

Routine Playwright artifacts belong in ignored `test-results/` or `playwright-report/`.

Before promoting an artifact into `output/playwright/`:

1. Confirm all visible content is deterministic fixture data.
2. Confirm no cookies, storage state, tokens, headers, real prompts, real articles, annotations, or account identifiers are present.
3. Record route, viewport, browser project, theme, fixture state, command, exit status, and SHA in a small manifest.
4. Use video mainly for failed interaction diagnosis; do not commit videos by default.
5. Hash only artifacts that have been reviewed.

Do not treat a broad pixel snapshot as the first release gate. Begin with semantic, geometry, state, and interaction assertions; promote only stable, narrowly scoped screenshots to regression gates.

## 7. Audit lenses

Evaluate every finding through these lenses:

### State truth

Loading, empty, error, retry, stale data, and success must be mutually understandable. Empty is valid only after a successful empty response. Old content must not masquerade as the result for a new URL/module/cursor.

### Research-flow continuity

Check article entry, Back, refresh, list position/highlight, `module`, sort, language, query, cursor trail, and relevant local preferences. A visually attractive page that loses research context is a regression.

### Visual hierarchy and editorial craft

Judge information order, action priority, scan rhythm, reading measure, typography, density, and status emphasis. Preserve the existing warm-paper/warm-charcoal editorial direction unless evidence shows it blocks a task. Do not recommend decorative gradients, glow, particles, or purposeless motion as substitutes for clearer structure.

### Accessibility

Inspect landmarks, headings, names, roles, keyboard order, skip navigation, focus visibility/restoration, dialogs/menus, live status, reduced motion, reflow, and contrast. Axe is supporting evidence; it does not replace keyboard or screen-reader-oriented inspection. If `color-contrast` is disabled, do not claim WCAG AA contrast completion.

### Responsive and input behavior

Check representative widths and breakpoint boundaries. Ensure sidebar/drawer/bottom navigation, sticky controls, retry actions, safe areas, touch targets, and overlays remain available without overlap or horizontal overflow.

### Privacy and authorization

Ensure browser evidence uses local fixtures, private cache ownership remains isolated, and no visual test weakens the current API/auth boundary. Never propose client-side shortcuts around FastAPI ownership or Miniflux source-of-truth rules.

### Performance and motion

Use existing performance baselines where relevant. Separate cold, warm HTTP cache, and service-worker-controlled behavior. Treat local timing as diagnostic until comparable samples and thresholds exist.

### Maintainability

Prefer the smallest existing seam, local CSS tokens, shared interaction utilities, and focused tests. Avoid a stack rewrite, new global state framework, broad component library replacement, or unrelated reformatting.

## 8. Classify findings honestly

For each finding use exactly one status:

- `OBSERVED`: directly supported by source, command, browser, screenshot, trace, or test.
- `PLAUSIBLE`: source suggests a defect, but a failing proof is still needed.
- `IN_PROGRESS`: partial evidence exists; acceptance is not closed.
- `NEEDS_BASELINE`: no trustworthy measurement exists yet.
- `NOT APPLICABLE`: outside the current Reader Web goal, with a short reason.

Do not call something broken solely because it differs from a generic design trend. Tie it to a user task, project invariant, acceptance row, or measured regression.

## 9. Recommend the smallest next batch

Order recommendations by the current root goal, not by visual novelty:

1. Correctness and state truth.
2. Privacy/security boundary.
3. Accessibility and responsive/input blockers.
4. Measured performance/recovery.
5. Visual refinement and delight.

For each recommendation include:

- target acceptance row;
- exact files/seams likely involved;
- failing proof or baseline to create first;
- minimal candidate change;
- verification commands and browser path;
- rollback boundary;
- what must remain unchanged.

Do not edit the product while in audit-only mode.

## 10. Report structure

Use this structure:

```markdown
# Reader Web audit — <scope>

## Executive summary
- Current authority and priority
- Highest-confidence user-impact issue
- Smallest recommended next batch

## Evidence boundary
- SHA / branch / worktree status
- Fixtures and browser projects used
- Commands run and not run
- Privacy review result

## Findings
### <severity> — <short title>
- Status: OBSERVED | PLAUSIBLE | IN_PROGRESS | NEEDS_BASELINE | NOT APPLICABLE
- GOAL mapping: A-..
- Evidence: `path:line`, command, browser state, screenshot/trace
- User impact
- Existing seam to reuse
- Smallest next proof/change
- Verification and rollback

## Visual and interaction matrix
- Desktop/mobile
- Light/dark
- Loading/empty/error/retry/success
- Keyboard/pointer/touch-equivalent

## Preserved invariants
- Sanitization
- Agent Markdown/think stripping
- URL/context restoration
- saved→project
- auth/demo/cache boundaries

## Next batch
- One bounded implementation slice, or `No product change recommended`
```

Report only observed command results. If browser driving, screenshots, contrast, or cross-engine checks were not run, say so explicitly.
