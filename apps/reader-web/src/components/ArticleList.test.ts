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
      selectedArticleId: null,
    });

  assert.match(html, /暂无文章/);
  assert.match(html, /当前模块没有可显示的文章/);
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
    score: null,
    readLater: false,
    lastReadAt: null,
  };

  const html = renderArticleList({
      articles: [article],
      currentModule: "all",
      currentSort: "technical",
      currentLang: "zh",
      selectedArticleId: 42,
    });

  assert.match(html, /这是一段中文摘要/);
  assert.match(html, /data-preview-href="\?module=all&amp;sort=technical&amp;lang=zh&amp;article=42"/);
  assert.match(html, /href="\/read\/42\?module=all&amp;sort=technical&amp;lang=zh"/);
  assert.match(html, /单击预览，双击进入专注阅读/);
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
      selectedArticleId: null,
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
      selectedArticleId: null,
    });

  assert.doesNotMatch(html, /重评/);
  assert.doesNotMatch(html, /评分设置/);
  assert.doesNotMatch(html, /<select/);
  assert.match(html, /sortMenuButton/);
});
