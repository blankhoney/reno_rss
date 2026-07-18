import assert from "node:assert/strict";
import test from "node:test";
import {
  buildWorkbenchCommands,
  filterCommands,
  isCommandPaletteToggle,
  isEditableKeyboardTarget,
  moveCommandIndex,
  moduleHref,
  normalizeCommandQuery,
} from "./commandPalette";

test("moduleHref encodes module sort lang", () => {
  assert.equal(moduleHref("project", "score", "original"), "/?module=project&sort=score&lang=original");
});

test("buildWorkbenchCommands covers core navigation surfaces", () => {
  const commands = buildWorkbenchCommands();
  const ids = new Set(commands.map((command) => command.id));
  assert.ok(ids.has("nav-home"));
  assert.ok(ids.has("nav-all"));
  assert.ok(ids.has("nav-starred"));
  assert.ok(ids.has("nav-project"));
  assert.ok(ids.has("nav-search"));
  assert.ok(ids.has("nav-admin"));
  assert.ok(ids.has("action-theme"));
});

test("filterCommands matches labels and keywords case-insensitively", () => {
  const commands = buildWorkbenchCommands();
  const byLabel = filterCommands(commands, "立项");
  assert.ok(byLabel.some((command) => command.id === "nav-project"));
  const byKeyword = filterCommands(commands, "candidate");
  assert.ok(byKeyword.some((command) => command.id === "nav-starred"));
  const noMatch = filterCommands(commands, "zzz-no-match");
  // Free-text always offers article search, even when no static commands match.
  assert.equal(noMatch.length, 1);
  assert.equal(noMatch[0].id.startsWith("search-articles:"), true);
});

test("normalizeCommandQuery trims and lowercases", () => {
  assert.equal(normalizeCommandQuery("  Admin  "), "admin");
});

test("moveCommandIndex wraps around", () => {
  assert.equal(moveCommandIndex(0, -1, 3), 2);
  assert.equal(moveCommandIndex(2, 1, 3), 0);
  assert.equal(moveCommandIndex(0, 1, 0), 0);
});

test("isCommandPaletteToggle accepts meta/ctrl + k", () => {
  assert.equal(isCommandPaletteToggle({ key: "k", metaKey: true, ctrlKey: false }), true);
  assert.equal(isCommandPaletteToggle({ key: "K", metaKey: false, ctrlKey: true }), true);
  assert.equal(isCommandPaletteToggle({ key: "k", metaKey: false, ctrlKey: false }), false);
});

test("isEditableKeyboardTarget detects form fields", () => {
  const input = { isContentEditable: false, tagName: "INPUT" } as unknown as HTMLElement;
  const div = { isContentEditable: false, tagName: "DIV" } as unknown as HTMLElement;
  assert.equal(isEditableKeyboardTarget(input), true);
  assert.equal(isEditableKeyboardTarget(div), false);
  assert.equal(isEditableKeyboardTarget(null), false);
});

test("filterCommands prepends free-text article search jump", () => {
  const commands = buildWorkbenchCommands();
  const filtered = filterCommands(commands, "zephyr quantum");
  assert.ok(filtered.length >= 1);
  assert.equal(filtered[0].id.startsWith("search-articles:"), true);
  assert.equal(filtered[0].href, "/?module=search&sort=default&lang=zh&q=zephyr+quantum");
});
