import assert from "node:assert/strict";
import test from "node:test";

import { ARTICLE_AGENT_LIMITS, parseArticleAgentRequest } from "./request";

function payload(overrides: Record<string, unknown> = {}) {
  return {
    question: "总结这篇文章",
    article: {
      title: "Article",
      url: "https://example.com",
      contentText: "Body",
      contentStatus: "partial",
      scoreReason: "",
      tags: [],
    },
    ...overrides,
  };
}

test("parseArticleAgentRequest accepts a minimal valid payload", () => {
  const result = parseArticleAgentRequest(payload());

  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.value.question, "总结这篇文章");
    assert.equal(result.value.article.contentStatus, "partial");
  }
});

test("parseArticleAgentRequest defaults missing contentStatus to full", () => {
  const base = payload();
  delete (base.article as Record<string, unknown>).contentStatus;
  const result = parseArticleAgentRequest(base);

  assert.equal(result.ok, true);
  if (result.ok) {
    assert.equal(result.value.article.contentStatus, "full");
  }
});

test("parseArticleAgentRequest rejects oversized prompt fields", () => {
  assert.deepEqual(
    parseArticleAgentRequest(payload({ question: "x".repeat(ARTICLE_AGENT_LIMITS.question + 1) })),
    { ok: false, error: "Question is too long" },
  );
  assert.deepEqual(
    parseArticleAgentRequest(
      payload({
        article: {
          title: "Article",
          url: "https://example.com",
          contentText: "x".repeat(ARTICLE_AGENT_LIMITS.contentText + 1),
          scoreReason: "",
          tags: [],
        },
      }),
    ),
    { ok: false, error: "Article content is too long" },
  );
  assert.deepEqual(
    parseArticleAgentRequest(
      payload({ selectedText: "x".repeat(ARTICLE_AGENT_LIMITS.selectedText + 1) }),
    ),
    { ok: false, error: "Selected text is too long" },
  );
});
