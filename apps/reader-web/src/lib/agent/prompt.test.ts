import assert from "node:assert/strict";
import test from "node:test";
import { buildArticleAgentMessages, shouldUseWebSearch } from "./prompt";

test("shouldUseWebSearch detects freshness questions", () => {
  assert.equal(shouldUseWebSearch("这个库现在还推荐用吗？版本是不是最新？"), true);
  assert.equal(shouldUseWebSearch("总结这篇文章"), false);
  assert.equal(shouldUseWebSearch("总结这篇文章", "partial"), true);
});

test("buildArticleAgentMessages includes selected quote", () => {
  const messages = buildArticleAgentMessages({
    question: "解释这段",
    article: {
      title: "Agent Article",
      url: "https://example.com",
      contentText: "Full content",
      contentStatus: "full",
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

test("buildArticleAgentMessages discloses partial content and search status", () => {
  const messages = buildArticleAgentMessages({
    question: "文章说了什么",
    article: {
      title: "Partial Article",
      url: "https://example.com",
      contentText: "Short RSS fragment",
      contentStatus: "partial",
      scoreReason: "",
      tags: [],
    },
    searchResults: [],
    searchStatus: "not_configured",
  });

  const serialized = JSON.stringify(messages);
  assert.match(serialized, /RSS 片段/);
  assert.match(serialized, /联网补充未配置/);
});
