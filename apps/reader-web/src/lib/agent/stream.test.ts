import assert from "node:assert/strict";
import test from "node:test";

import {
  cleanOpenAICompatibleSseStream,
  createThinkTagFilter,
  extractOpenAICompatibleEventText,
  stripThinkTags,
} from "./stream";

function sseData(content: string): string {
  return `data: ${JSON.stringify({ choices: [{ delta: { content } }] })}\n\n`;
}

function streamFromStrings(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

async function readStream(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let output = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    output += decoder.decode(value, { stream: true });
  }

  return output + decoder.decode();
}

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

test("cleanOpenAICompatibleSseStream removes model reasoning from server stream", async () => {
  const cleaned = await readStream(
    cleanOpenAICompatibleSseStream(
      streamFromStrings([sseData("<think>hidden</think>## 结论\n可以"), "data: [DONE]\n\n"]),
    ),
  );

  assert.equal(cleaned, `${sseData("## 结论\n可以")}data: [DONE]\n\n`);
});

test("cleanOpenAICompatibleSseStream removes cross-chunk reasoning", async () => {
  const cleaned = await readStream(
    cleanOpenAICompatibleSseStream(
      streamFromStrings([
        sseData("<thi"),
        sseData("nk>hidden"),
        sseData(" still hidden</th"),
        sseData("ink>## 结论\n可以"),
        "data: [DONE]\n\n",
      ]),
    ),
  );

  assert.equal(cleaned, `${sseData("## 结论\n可以")}data: [DONE]\n\n`);
});
