import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_TYPEWRITER_INTERVAL_MS, prefersReducedMotion, takeTypewriterChunk } from "./typewriter";

test("takeTypewriterChunk reveals a bounded chunk", () => {
  assert.deepEqual(takeTypewriterChunk("abcdef", 2, 4), {
    chunk: "ab",
    rest: "cdef",
  });
});

test("takeTypewriterChunk clamps to at least one and at most max chars", () => {
  assert.deepEqual(takeTypewriterChunk("abcdef", 0, 4), {
    chunk: "a",
    rest: "bcdef",
  });
  assert.deepEqual(takeTypewriterChunk("abcdef", 8, 3), {
    chunk: "abc",
    rest: "def",
  });
});

test("default typewriter interval stays in the reviewed V3 range", () => {
  assert.equal(DEFAULT_TYPEWRITER_INTERVAL_MS >= 48, true);
  assert.equal(DEFAULT_TYPEWRITER_INTERVAL_MS <= 64, true);
});

test("prefersReducedMotion is false without a browser media query", () => {
  assert.equal(prefersReducedMotion(), false);
});
