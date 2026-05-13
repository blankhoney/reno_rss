import assert from "node:assert/strict";
import test from "node:test";

import { extractOpenAICompatibleEventText } from "./stream";

test("extractOpenAICompatibleEventText reads streaming delta content", () => {
  const data = JSON.stringify({ choices: [{ delta: { content: "你好" } }] });

  assert.equal(extractOpenAICompatibleEventText(data), "你好");
});

test("extractOpenAICompatibleEventText ignores done and malformed events", () => {
  assert.equal(extractOpenAICompatibleEventText("[DONE]"), "");
  assert.equal(extractOpenAICompatibleEventText("not json"), "");
});
