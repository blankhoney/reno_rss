# Reader Web audit checklist

Use only the sections relevant to the selected page or flow. This checklist supports the skill; it is not authority over `AGENTS.md`, `GOAL.md`, or current source.

## Contents

1. Evidence boundary
2. State truth
3. Navigation continuity
4. Visual hierarchy
5. Accessibility
6. Responsive/input
7. Reader safety
8. PWA/privacy
9. Performance/motion
10. Suggested pairwise matrix

## 1. Evidence boundary

- [ ] Record branch, SHA, and `git status --short`.
- [ ] Identify user-owned uncommitted files; do not edit or stage them.
- [ ] Record exact fixture and browser project.
- [ ] Separate commands actually run from planned commands.
- [ ] Inspect promoted screenshots/videos for fixture-only content.
- [ ] Exclude cookies, storage state, auth headers, `.env`, real articles, user annotations, prompts, and provider output.

## 2. State truth

For each owned resource, check mutual visibility and semantic messaging:

- [ ] Initial loading.
- [ ] Server-confirmed success with content.
- [ ] Server-confirmed successful empty response.
- [ ] Partial success when a secondary resource fails.
- [ ] Initial error.
- [ ] Non-initial refresh/pagination error.
- [ ] Retry pending.
- [ ] Retry success.
- [ ] Retry exhaustion, where applicable.
- [ ] Stale/obsolete request ignored.
- [ ] No old content presented as current URL/module/cursor success.
- [ ] Error copy names the failed resource and offers the correct recovery action.

## 3. Navigation continuity

- [ ] Article href preserves module, sort, language, query, cursor trail, and source article ID.
- [ ] Browser Back restores the expected list and card.
- [ ] Refresh restores URL-backed state.
- [ ] Return highlight is visible and not hidden by sticky UI.
- [ ] Local craft preferences survive navigation without becoming fake API filters.
- [ ] Search/research/citation targets retain their intended context.

## 4. Visual hierarchy

- [ ] Primary task and next action are visually dominant.
- [ ] Status/error/retry is not visually subordinate to stale content.
- [ ] Metadata, title, summary, score, and actions have a consistent reading order.
- [ ] Long title, URL, feed name, tags, and untranslated content wrap safely.
- [ ] Reading measure and paragraph rhythm support long-form reading.
- [ ] Density differences help a task rather than merely shrinking controls.
- [ ] Light and dark themes express the same semantic hierarchy.
- [ ] Motion communicates state and respects reduced motion.

## 5. Accessibility

- [ ] One clear primary-content landmark and no invalid nested landmarks.
- [ ] Skip navigation is present where repeated shell controls precede content.
- [ ] Heading order is meaningful.
- [ ] Controls have accessible names and state (`aria-current`, expanded, selected, busy).
- [ ] Keyboard order follows visual/task order.
- [ ] Focus is visible in light/dark and restored after dismissing layers.
- [ ] Dialogs, menus, and drawers trap/dismiss correctly without hiding active controls.
- [ ] Live regions announce status without excessive repetition.
- [ ] Contrast checks include normal text, muted text, links, buttons, errors, disabled states, and focus rings.
- [ ] Reflow works at narrow widths and zoom-equivalent layouts.
- [ ] Axe exclusions are listed; excluded contrast means contrast is not complete.

## 6. Responsive and input

- [ ] No horizontal overflow at representative widths and breakpoint edges.
- [ ] Sidebar, drawer, and bottom nav never all disappear.
- [ ] Sticky headers/bars do not cover content, focus, or retry actions.
- [ ] Safe-area inset protects mobile bottom actions and toasts.
- [ ] Touch targets are large enough and do not overlap.
- [ ] Pointer, keyboard, and touch-equivalent paths have the same outcome.
- [ ] Native touch selection is not inferred from programmatic range creation.
- [ ] Orientation/height constraints do not strand modal or drawer actions.

## 7. Reader safety

- [ ] Article HTML passes `sanitizeArticleHtml()` before render.
- [ ] Agent output uses `AgentMarkdown`, not raw HTML.
- [ ] Stream cleanup strips fragmented `<think>` content.
- [ ] Annotation anchoring prefers explicit unresolved state over wrong binding.
- [ ] Saved/project actions use FastAPI state APIs and preserve `project ⇒ saved`.
- [ ] Content-quality fallback remains explicit.

## 8. PWA and privacy

- [ ] Private article cache ownership changes clear the prior owner's cache.
- [ ] Logout clears private cached article details.
- [ ] Offline claims match the real limited scope.
- [ ] No visual fixture uses production/user content.
- [ ] Screenshots/videos do not expose authentication or private state.
- [ ] Staging anonymous demo behavior is not generalized to production.

## 9. Performance and motion

- [ ] Readiness marker represents actual usable content.
- [ ] Cold, warm HTTP cache, and service-worker-controlled samples are separated.
- [ ] Comparable environment/sample count is recorded.
- [ ] Browser/network errors fail the measurement.
- [ ] Local values are not promoted to CI budgets without noise analysis.
- [ ] Reduced motion preserves visibility and interaction order.

## 10. Suggested pairwise matrix

Use the smallest set that covers the current claim:

| Dimension | Representative values |
| --- | --- |
| Width | 320, 390, 768, 899/901, 1024, 1280, 1440 |
| Browser | Chromium, Firefox, WebKit, iPhone WebKit |
| Theme | light, dark |
| Input | keyboard, pointer, touch-equivalent |
| State | loading, empty, error, retry, success, long content |
| Flow | list, article entry, Back, refresh, overlay dismiss |

Do not run every combination by default. Choose pairwise cases that can falsify the specific claim and disclose what remains untested.
