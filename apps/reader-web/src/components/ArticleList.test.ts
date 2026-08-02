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

test("ArticleList keeps a previous-page escape for a successful later empty page", () => {
  const firstPage = renderArticleList({
    articles: [],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    pageIndex: 0,
    hasPrev: false,
    hasNext: false,
    onPrev: () => {},
    onNext: () => {},
  });
  const laterPage = renderArticleList({
    articles: [],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    pageIndex: 1,
    hasPrev: true,
    hasNext: false,
    onPrev: () => {},
    onNext: () => {},
  });

  assert.doesNotMatch(firstPage, /articleListPager/);
  assert.match(laterPage, /暂无文章/);
  assert.match(laterPage, /articleListPager/);
  assert.match(laterPage, />‹ 上一页<\/button>/);
  assert.match(laterPage, /第 2 页/);
});

test("ArticleList renders skeleton cards while loading instead of empty copy", () => {
  const html = renderArticleList({
      articles: [],
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
      isLoading: true,
    });

  assert.match(html, /文章加载中/);
  assert.equal((html.match(/articleCardSkeleton/g) ?? []).length, 12);
  assert.match(html, /articleCardHeadline/);
  assert.doesNotMatch(html, /暂无文章/);
});

test("ArticleList does not render empty copy or a focusable list while loading failed", () => {
  const html = renderArticleList({
    articles: [],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    loadError: "文章列表暂不可用",
    hasPrev: true,
    onPrev: () => {},
    onRetry: () => {},
  });

  assert.match(html, /文章加载失败/);
  assert.match(html, /文章列表暂不可用/);
  assert.match(html, />重试<\/button>/);
  assert.match(html, />‹ 上一页<\/button>/);
  assert.doesNotMatch(html, /暂无文章/);
  assert.doesNotMatch(html, /<ul/);
  assert.doesNotMatch(html, /articleListPager/);
});

test("ArticleList renders pager controls with disabled state", () => {
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
    project: false,
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
    myFeedback: null,
    readLater: false,
    lastReadAt: null,
  };

  const withMore = renderArticleList({
    articles: [article],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    pageIndex: 0,
    hasPrev: false,
    hasNext: true,
    onPrev: () => {},
    onNext: () => {},
  });
  const withoutMore = renderArticleList({
    articles: [article],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    pageIndex: 2,
    hasPrev: true,
    hasNext: false,
    onPrev: () => {},
    onNext: () => {},
  });

  assert.match(withMore, /‹ 上一页/);
  assert.match(withMore, /第 1 页/);
  assert.match(withMore, /下一页 ›/);
  assert.match(withMore, /<button type="button" class="articleListPagerBtn" disabled="">‹ 上一页/);
  assert.match(withoutMore, /第 3 页/);
  assert.match(withoutMore, /下一页 ›<\/button>/);
  assert.match(withoutMore, /<button type="button" class="articleListPagerBtn" disabled="">下一页/);
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
    project: false,
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
    myFeedback: null,
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
  assert.match(html, /articleCardHeadline/);
  assert.match(html, /scoreRing66/);
  assert.match(html, /88/);
  assert.match(html, /必读/);
  assert.doesNotMatch(html, /data-preview-href/);
  assert.match(html, /href="\/read\/42\?module=all&amp;sort=technical&amp;lang=zh"/);
  assert.match(html, /进入专注阅读/);
  assert.match(html, /data-article-id="42"/);
  assert.doesNotMatch(html, /role="link"/);
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
          project: false,
          publishedAt: "2026-05-14T00:00:00Z",
          score: null,
          myFeedback: null,
          readLater: false,
          lastReadAt: null,
        },
      ],
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
    });

  assert.match(html, /暂无摘要/);
  assert.match(html, /评分完成后自动生成/);
  assert.match(html, /scoreRingEmpty/);
  assert.match(html, /未评/);
  assert.doesNotMatch(html, /层级/);
  assert.doesNotMatch(html, /<p class="articleCardSummary">未评分<\/p>/);
  assert.doesNotMatch(html, /未生成摘要/);
});

test("ArticleList exposes a focusable keyboard scope instead of a global shortcut target", () => {
  const html = renderArticleList({
    articles: [],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
  });

  assert.match(html, /class="articleList"[^>]*tabindex="0"/);
});

test("ArticleList renders row numbers after the first-page headline", () => {
  const baseArticle: Article = {
    id: 50,
    userId: 1,
    feedId: 2,
    feedTitle: "Feed",
    categoryId: null,
    categoryTitle: "",
    title: "Title",
    url: "https://example.com",
    contentHtml: "<p>Body</p>",
    contentStatus: "partial",
    contentIssue: "rss_fragment",
    contentFetchAttempted: false,
    summaryZh: "摘要",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: "unread",
    starred: false,
    project: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: null,
    myFeedback: null,
    readLater: false,
    lastReadAt: null,
  };
  const html = renderArticleList({
    articles: [
      { ...baseArticle, id: 50, title: "Headline" },
      { ...baseArticle, id: 51, title: "Second" },
      { ...baseArticle, id: 52, title: "Third" },
    ],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
  });

  assert.match(html, /articleCardHeadline/);
  assert.match(html, />01<\/span>/);
  assert.match(html, />02<\/span>/);
});

test("ArticleList highlights the article restored from focus reading", () => {
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
    summaryZh: "摘要",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: "unread",
    starred: false,
    project: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: null,
    myFeedback: null,
    readLater: false,
    lastReadAt: null,
  };

  const html = renderArticleList({
    articles: [article],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
    highlightArticleId: 42,
  });

  assert.match(html, /articleCardReturnTarget/);
});

test("ArticleList marks read articles for quieter visual treatment", () => {
  const article: Article = {
    id: 44,
    userId: 1,
    feedId: 2,
    feedTitle: "Feed",
    categoryId: 3,
    categoryTitle: "AI",
    title: "Read title",
    url: "https://example.com/read",
    contentHtml: "<p>Body</p>",
    contentStatus: "partial",
    contentIssue: "rss_fragment",
    contentFetchAttempted: false,
    summaryZh: "摘要",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: "read",
    starred: false,
    project: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: null,
    myFeedback: null,
    readLater: false,
    lastReadAt: "2026-05-14T00:00:01Z",
  };

  const html = renderArticleList({
    articles: [article],
    currentModule: "all",
    currentSort: "default",
    currentLang: "zh",
  });

  assert.match(html, /articleCardRead/);
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
          project: false,
          publishedAt: "2026-05-14T00:00:00Z",
          score: null,
          myFeedback: null,
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
