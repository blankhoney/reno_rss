import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ArticleList, failedScoreMessages, scoreErrorMessage } from "./ArticleList";
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
  assert.match(html, /data-preview-href="\?module=all&amp;sort=technical&amp;lang=zh&amp;article=42"/);
  assert.match(html, /href="\/read\/42\?module=all&amp;sort=technical&amp;lang=zh"/);
  assert.match(html, /单击预览，双击进入专注阅读/);
  assert.match(html, /阅读/);
});

test("ArticleList uses low-noise summary text for unscored articles", () => {
  const html = renderToStaticMarkup(
    React.createElement(ArticleList, {
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
    }),
  );

  assert.match(html, /未评分/);
  assert.doesNotMatch(html, /未生成摘要/);
});

test("scoreErrorMessage translates common bulk scoring failures", () => {
  assert.equal(scoreErrorMessage("manual_rescore_disabled"), "手动重评已关闭");
  assert.equal(scoreErrorMessage("entry_not_found"), "文章不存在或不在当前 Miniflux 实例");
  assert.equal(scoreErrorMessage(undefined), "未知错误");
});

test("failedScoreMessages keeps partial failure details", () => {
  assert.deepEqual(
    failedScoreMessages({
      total: 3,
      completed: 3,
      succeeded: 2,
      failed: 1,
      results: [
        { ok: true, entryId: 1 },
        { ok: false, entryId: 2, error: "score_failed" },
        { ok: true, entryId: 3 },
      ],
    }),
    ["#2：评分失败"],
  );
});
