import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { ArticleList } from "./ArticleList";
import type { Article } from "@/lib/articles/types";

const appRouter = {
  back() {},
  forward() {},
  prefetch() {},
  push() {},
  replace() {},
  refresh() {},
};

function renderArticleList(props: React.ComponentProps<typeof ArticleList>) {
  return renderToStaticMarkup(
    React.createElement(
      AppRouterContext.Provider,
      { value: appRouter as never },
      React.createElement(ArticleList, props),
    ),
  );
}

test("ArticleList renders an explicit empty state", () => {
  const html = renderArticleList({
      articles: [],
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
    });

  assert.match(html, /暂无文章/);
  assert.match(html, /当前模块没有可显示的文章/);
});

test("ArticleList shows the load-more control only when more pages exist", () => {
  const article: Article = {
    id: 7,
    userId: 1,
    feedId: 2,
    feedTitle: "Feed",
    categoryId: null,
    categoryTitle: "",
    title: "Paged title",
    url: "https://example.com/paged",
    contentHtml: "<p>Body</p>",
    contentStatus: "partial",
    contentIssue: "rss_fragment",
    contentFetchAttempted: false,
    summaryZh: "摘要",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: "unread",
    starred: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: {
      overall: 88,
      tier: "must_read",
      dimensions: { topic_relevance: 88 },
      tags: [],
      reason: "值得阅读",
      summaryZh: "这是一段中文摘要。",
      summaryOriginal: "This is an original summary.",
      sourceLanguage: "en",
      dimensionReasons: {},
      scoredAt: "2026-05-14T00:00:00Z",
    },
    readLater: false,
    lastReadAt: null,
  };

  const withMore = renderArticleList({
    articles: [article],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    hasMore: true,
    onLoadMore: () => {},
  });
  const withoutMore = renderArticleList({
    articles: [article],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    hasMore: false,
    onLoadMore: () => {},
  });

  assert.match(withMore, /加载更多/);
  assert.match(withMore, /已加载 1 篇 · 还有更多/);
  assert.match(withoutMore, /已加载 1 篇 · 已全部加载/);
  assert.doesNotMatch(withoutMore, /加载更多/);
});

test("ArticleList renders summaries and preserves workbench and focus reading links", () => {
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
    contentIssue: "rss_fragment",
    contentFetchAttempted: false,
    summaryZh: "这是一段中文摘要。",
    summaryOriginal: "This is an original summary.",
    sourceLanguage: "en",
    status: "unread",
    starred: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: {
      overall: 88,
      tier: "must_read",
      dimensions: { topic_relevance: 88 },
      tags: [],
      reason: "值得阅读",
      summaryZh: "这是一段中文摘要。",
      summaryOriginal: "This is an original summary.",
      sourceLanguage: "en",
      dimensionReasons: {},
      scoredAt: "2026-05-14T00:00:00Z",
    },
    readLater: false,
    lastReadAt: null,
  };

  const html = renderArticleList({
      articles: [article],
      currentModule: "all",
      currentSort: "technical",
      currentLang: "zh",
    });

  assert.match(html, /这是一段中文摘要/);
  assert.match(html, /总分/);
  assert.match(html, /88/);
  assert.match(html, /层级/);
  assert.match(html, /必读/);
  assert.doesNotMatch(html, /data-preview-href/);
  assert.match(html, /href="\/read\/42\?module=all&amp;sort=technical&amp;lang=zh"/);
  assert.match(html, /进入专注阅读/);
  assert.match(html, /阅读/);
});

test("ArticleList uses low-noise summary text for unscored articles", () => {
  const html = renderArticleList({
      articles: [
        {
          id: 43,
          userId: 1,
          feedId: 2,
          feedTitle: "Feed",
          categoryId: 3,
          categoryTitle: "AI",
          title: "Unscored title",
          url: "https://example.com/unscored",
          contentHtml: "<p>Body</p>",
          contentStatus: "partial",
          contentIssue: "rss_fragment",
          contentFetchAttempted: false,
          summaryZh: "",
          summaryOriginal: "",
          sourceLanguage: "unknown",
          status: "unread",
          starred: false,
          publishedAt: "2026-05-14T00:00:00Z",
          score: null,
          readLater: false,
          lastReadAt: null,
        },
      ],
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
    });

  assert.match(html, /未评分/);
  assert.doesNotMatch(html, /未生成摘要/);
});

test("ArticleList keeps list actions on FastAPI-backed reading controls", () => {
  const html = renderArticleList({
      articles: [
        {
          id: 43,
          userId: 1,
          feedId: 2,
          feedTitle: "Feed",
          categoryId: 3,
          categoryTitle: "AI",
          title: "Article title",
          url: "https://example.com/article",
          contentHtml: "<p>Body</p>",
          contentStatus: "partial",
          contentIssue: "rss_fragment",
          contentFetchAttempted: false,
          summaryZh: "",
          summaryOriginal: "",
          sourceLanguage: "unknown",
          status: "unread",
          starred: false,
          publishedAt: "2026-05-14T00:00:00Z",
          score: null,
          readLater: false,
          lastReadAt: null,
        },
      ],
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
    });

  assert.doesNotMatch(html, /重评/);
  assert.doesNotMatch(html, /评分设置/);
  assert.doesNotMatch(html, /<select/);
  assert.match(html, /sortMenuButton/);
});
