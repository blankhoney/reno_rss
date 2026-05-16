import assert from "node:assert/strict";
import test from "node:test";
import type { Article } from "@/lib/articles/types";
import { buildFeedQualitySummaries } from "./quality";

function article(id: number, input: Partial<Article> = {}): Article {
  return {
    id,
    userId: 1,
    feedId: input.feedId ?? 1,
    feedTitle: input.feedTitle ?? "Feed",
    categoryId: null,
    categoryTitle: "未分类",
    title: `Article ${id}`,
    url: "https://example.com",
    contentHtml: "<p>Body</p>",
    contentStatus: input.contentStatus ?? "full",
    contentIssue: input.contentIssue ?? null,
    contentFetchAttempted: false,
    summaryZh: "",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: input.status ?? "unread",
    starred: input.starred ?? false,
    publishedAt: "2026-05-14T00:00:00.000Z",
    score: input.score ?? null,
    readLater: input.readLater ?? false,
    lastReadAt: input.lastReadAt ?? null,
  };
}

test("buildFeedQualitySummaries computes content and behavior quality", () => {
  const summaries = buildFeedQualitySummaries({
    feeds: [{ id: 1, title: "Strong" }, { id: 2, title: "Weak" }],
    articles: [
      article(1, {
        feedId: 1,
        feedTitle: "Strong",
        starred: true,
        score: {
          overall: 85,
          dimensions: {
            importance: 85,
            usefulness: 85,
            timeliness: 85,
            depth: 85,
            technical_value: 85,
            business_value: 85,
            trend_value: 85,
          },
          tags: [],
          reason: "",
          summaryZh: "",
          summaryOriginal: "",
          sourceLanguage: "unknown",
          dimensionReasons: {},
          scoredAt: null,
        },
      }),
      article(2, {
        feedId: 2,
        feedTitle: "Weak",
        contentStatus: "partial",
        contentIssue: "blocked_or_error_page",
      }),
    ],
    preferences: new Map([[2, { feedId: 2, hidden: true, hiddenAt: null, updatedAt: null }]]),
    projectEntryIds: new Set([1]),
  });

  const strong = summaries.find((summary) => summary.id === 1);
  const weak = summaries.find((summary) => summary.id === 2);
  assert.ok(strong);
  assert.ok(weak);
  assert.equal(strong.fullCount, 1);
  assert.equal(strong.averageScore, 85);
  assert.equal(strong.projectCount, 1);
  assert.equal(weak.hidden, true);
  assert.equal(weak.blockedCount, 1);
  assert.ok(strong.qualityScore > weak.qualityScore);
});
