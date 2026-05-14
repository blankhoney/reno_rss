import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ArticleList } from "./ArticleList";
import type { Article } from "@/lib/articles/types";

test("ArticleList renders an explicit empty state", () => {
  const html = renderToStaticMarkup(
    React.createElement(ArticleList, {
      articles: [],
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
      selectedArticleId: null,
    }),
  );

  assert.match(html, /暂无文章/);
  assert.match(html, /当前模块没有可显示的文章/);
});

test("ArticleList renders summaries and preserves module sort lang in article links", () => {
  const article: Article = {
    id: 42,
    userId: 1,
    feedId: 2,
    feedTitle: "Feed",
    categoryId: 3,
    categoryTitle: "AI",
    title: "Example title",
    url: "https://example.com",
    contentHtml: "<p>Body</p>",
    contentStatus: "partial",
    contentFetchAttempted: false,
    summaryZh: "这是一段中文摘要。",
    summaryOriginal: "This is an original summary.",
    sourceLanguage: "en",
    status: "unread",
    starred: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: null,
    readLater: false,
    lastReadAt: null,
  };

  const html = renderToStaticMarkup(
    React.createElement(ArticleList, {
      articles: [article],
      currentModule: "all",
      currentSort: "technical",
      currentLang: "zh",
      selectedArticleId: 42,
    }),
  );

  assert.match(html, /这是一段中文摘要/);
  assert.match(html, /module=all&amp;sort=technical&amp;lang=zh&amp;article=42/);
});
