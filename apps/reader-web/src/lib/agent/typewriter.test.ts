import assert from "node:assert/strict";
import test from "node:test";

import { takeTypewriterChunk } from "./typewriter";

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
