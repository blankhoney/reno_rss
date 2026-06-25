import assert from "node:assert/strict";
import test from "node:test";
import type { Article } from "@/lib/articles/types";
import { buildWorkbenchView } from "./ReaderWorkbench";

function article(id: number, input: Partial<Article> = {}): Article {
  return {
    id,
    userId: 1,
    feedId: 1,
    feedTitle: "Feed",
    feedHidden: input.feedHidden,
    feedQualityScore: input.feedQualityScore,
    categoryId: null,
    categoryTitle: "",
    title: `Article ${id}`,
    url: `https://example.com/${id}`,
    contentHtml: "",
    contentStatus: "partial",
    contentIssue: "rss_fragment",
    contentFetchAttempted: false,
    summaryZh: "",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: input.status ?? "unread",
    starred: input.starred ?? false,
    publishedAt: input.publishedAt ?? "2026-06-25T00:00:00Z",
    score: null,
    readLater: input.readLater ?? false,
    lastReadAt: input.lastReadAt ?? null,
  };
}

test("buildWorkbenchView filters module articles and keeps an explicit selection", () => {
  const view = buildWorkbenchView({
    articles: [
      article(1, { status: "unread" }),
      article(2, { status: "read" }),
      article(3, { status: "unread", feedHidden: true }),
    ],
    currentModule: "unread",
    currentSort: "latest",
    requestedSelectedId: 1,
  });

  assert.equal(view.moduleId, "unread");
  assert.deepEqual(view.articles.map((item) => item.id), [1]);
  assert.equal(view.selectedArticleId, 1);
});

test("buildWorkbenchView falls back to the first visible article", () => {
  const view = buildWorkbenchView({
    articles: [
      article(1, { publishedAt: "2026-06-24T00:00:00Z" }),
      article(2, { publishedAt: "2026-06-25T00:00:00Z" }),
    ],
    currentModule: "all",
    currentSort: "latest",
    requestedSelectedId: null,
  });

  assert.deepEqual(view.articles.map((item) => item.id), [2, 1]);
  assert.equal(view.selectedArticleId, 2);
});
