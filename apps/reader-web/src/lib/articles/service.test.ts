import assert from "node:assert/strict";
import test from "node:test";
import { sortArticlesForModule } from "./service";
import type { Article } from "./types";

function article(id: number, technical: number, business: number): Article {
  return {
    id,
    userId: 1,
    feedId: 1,
    feedTitle: "Feed",
    categoryId: 1,
    categoryTitle: "AI",
    title: `Article ${id}`,
    url: "https://example.com",
    contentHtml: "<p>Body</p>",
    status: "unread",
    starred: false,
    publishedAt: "2026-05-13T00:00:00Z",
    readLater: false,
    lastReadAt: null,
    score: {
      overall: 70,
      dimensions: {
        importance: 70,
        usefulness: 70,
        timeliness: 70,
        depth: 70,
        technical_value: technical,
        business_value: business,
        trend_value: 70,
      },
      tags: ["ai"],
      reason: "reason",
      scoredAt: null,
    },
  };
}

test("technical module sorts by technical_value descending", () => {
  const sorted = sortArticlesForModule([article(1, 40, 90), article(2, 95, 10)], "technical");
  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
});

test("business module sorts by business_value descending", () => {
  const sorted = sortArticlesForModule([article(1, 40, 90), article(2, 95, 10)], "business");
  assert.deepEqual(sorted.map((item) => item.id), [1, 2]);
});
