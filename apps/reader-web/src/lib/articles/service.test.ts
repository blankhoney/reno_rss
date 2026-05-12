import assert from "node:assert/strict";
import test from "node:test";
import { sortArticlesForModule } from "./service";
import type { Article } from "./types";

function article(
  id: number,
  technical: number,
  business: number,
  lastReadAt: string | null = null,
): Article {
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
    lastReadAt,
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

test("read module sorts by lastReadAt descending (most recent first)", () => {
  const sorted = sortArticlesForModule(
    [
      article(1, 70, 70, "2026-05-01T00:00:00Z"),
      article(2, 70, 70, "2026-05-13T12:00:00Z"),
      article(3, 70, 70, null),
      article(4, 70, 70, "not-a-date"),
    ],
    "read",
  );
  assert.deepEqual(sorted.map((item) => item.id), [2, 1, 3, 4]);
});

test("ai module sorts by technical_value descending, not overall", () => {
  const lowTechnicalHighOverall = {
    ...article(1, 40, 90),
    score: { ...article(1, 40, 90).score!, overall: 99 },
  };
  const highTechnicalLowOverall = {
    ...article(2, 95, 10),
    score: { ...article(2, 95, 10).score!, overall: 1 },
  };
  const sorted = sortArticlesForModule([lowTechnicalHighOverall, highTechnicalLowOverall], "ai");
  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
});
