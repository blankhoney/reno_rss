import assert from "node:assert/strict";
import test from "node:test";

import { createThinkTagFilter, extractOpenAICompatibleEventText, stripThinkTags } from "./stream";

test("extractOpenAICompatibleEventText reads streaming delta content", () => {
  const data = JSON.stringify({ choices: [{ delta: { content: "你好" } }] });

  assert.equal(extractOpenAICompatibleEventText(data), "你好");
});

test("extractOpenAICompatibleEventText ignores done and malformed events", () => {
  assert.equal(extractOpenAICompatibleEventText("[DONE]"), "");
  assert.equal(extractOpenAICompatibleEventText("not json"), "");
});

test("stripThinkTags removes model reasoning blocks", () => {
  assert.equal(stripThinkTags("<think>hidden</think>## 结论\n可以"), "## 结论\n可以");
  assert.equal(stripThinkTags("<think>partial"), "");
});

test("createThinkTagFilter removes reasoning across streamed chunks", () => {
  const filter = createThinkTagFilter();

  assert.equal(filter.push("<thi"), "");
  assert.equal(filter.push("nk>hidden"), "");
  assert.equal(filter.push(" still hidden</th"), "");
  assert.equal(filter.push("ink>## 结论\n可以"), "## 结论\n可以");
  assert.equal(filter.flush(), "");
});
