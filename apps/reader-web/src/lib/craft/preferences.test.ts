import assert from "node:assert/strict";
import test from "node:test";
import {
  cycleReaderMode,
  DEFAULT_CRAFT_PREFERENCES,
  modeLabel,
  parseCraftPreferences,
} from "./preferences";

test("parseCraftPreferences falls back for invalid payloads", () => {
  assert.deepEqual(parseCraftPreferences(null), DEFAULT_CRAFT_PREFERENCES);
  assert.deepEqual(parseCraftPreferences({ mode: "nope" }).mode, "scan");
});

test("parseCraftPreferences accepts valid craft fields", () => {
  const parsed = parseCraftPreferences({
    mode: "focus",
    density: "compact",
    dualPane: true,
    pinnedThemes: ["rust", "llm", ""],
  });
  assert.equal(parsed.mode, "focus");
  assert.equal(parsed.density, "compact");
  assert.equal(parsed.dualPane, true);
  assert.deepEqual(parsed.pinnedThemes, ["rust", "llm"]);
});

test("cycleReaderMode rotates scan → focus → keep → scan", () => {
  assert.equal(cycleReaderMode("scan"), "focus");
  assert.equal(cycleReaderMode("focus"), "keep");
  assert.equal(cycleReaderMode("keep"), "scan");
});

test("modeLabel is bilingual", () => {
  assert.match(modeLabel("scan"), /扫描/);
  assert.match(modeLabel("focus"), /精读/);
  assert.match(modeLabel("keep"), /沉淀/);
});
