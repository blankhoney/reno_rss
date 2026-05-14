import assert from "node:assert/strict";
import test from "node:test";
import { buildArticleAgentMessages } from "./prompt";

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
  });

  const serialized = JSON.stringify(messages);
  assert.match(serialized, /Important quote/);
  assert.match(serialized, /High technical value/);
});

test("buildArticleAgentMessages discloses partial content without promising web search", () => {
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
  });

  const serialized = JSON.stringify(messages);
  assert.match(serialized, /RSS 片段/);
  assert.match(serialized, /未联网搜索/);
  assert.doesNotMatch(serialized, /联网补充/);
});
