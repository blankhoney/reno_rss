import assert from "node:assert/strict";
import test from "node:test";
import { buildArticleAgentMessages, shouldUseWebSearch } from "./prompt";

test("shouldUseWebSearch detects freshness questions", () => {
  assert.equal(shouldUseWebSearch("这个库现在还推荐用吗？版本是不是最新？"), true);
  assert.equal(shouldUseWebSearch("总结这篇文章"), false);
});

test("buildArticleAgentMessages includes selected quote", () => {
  const messages = buildArticleAgentMessages({
    question: "解释这段",
    article: {
      title: "Agent Article",
      url: "https://example.com",
      contentText: "Full content",
      scoreReason: "High technical value",
      tags: ["ai"],
    },
    selectedText: "Important quote",
    searchResults: [],
  });

  const serialized = JSON.stringify(messages);
  assert.match(serialized, /Important quote/);
  assert.match(serialized, /High technical value/);
});
