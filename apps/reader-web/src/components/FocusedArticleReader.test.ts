import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FocusedArticleReader } from "./FocusedArticleReader";
import type { Article } from "@/lib/articles/types";

function article(input: Partial<Article> = {}): Article {
  return {
    id: 42,
    userId: 1,
    feedId: 2,
    feedTitle: "Feed",
    categoryId: 3,
    categoryTitle: "AI",
    title: "Example title",
    url: "https://example.com",
    contentHtml: "<p>Short body</p>",
    contentStatus: "partial",
    contentFetchAttempted: true,
    summaryZh: "这是一段中文摘要。",
    summaryOriginal: "This is an original summary.",
    sourceLanguage: "en",
    status: "unread",
    starred: false,
    publishedAt: "2026-05-14T00:00:00Z",
    score: null,
    readLater: false,
    lastReadAt: null,
    ...input,
  };
}

test("FocusedArticleReader renders the focus reading controls and partial notice", () => {
  const html = renderToStaticMarkup(
    React.createElement(FocusedArticleReader, {
      article: article(),
      currentLang: "zh",
      returnHref: "/?module=all&sort=default&lang=zh&article=42",
      webSearchConfigured: false,
    }),
  );

  assert.match(html, /返回工作台/);
  assert.match(html, /打开原文/);
  assert.match(html, /刷新全文/);
  assert.match(html, /实时评分/);
  assert.match(html, /加入候选/);
  assert.match(html, /立项/);
  assert.match(html, /标记已读/);
  assert.doesNotMatch(html, /<summary>操作<\/summary>/);
  assert.match(html, /正文：片段/);
  assert.match(html, /评分：未评分/);
  assert.match(html, /联网补充：未配置/);
  assert.match(html, /当前仅有 RSS 片段/);
  assert.match(html, /文章助手/);
  assert.match(html, /总结、要点、解释选中、行动建议/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /agentDrawerBody/);
  assert.match(html, /inert=""/);
});

test("FocusedArticleReader renders scored state and dimension reasons", () => {
  const html = renderToStaticMarkup(
    React.createElement(FocusedArticleReader, {
      article: article({
        contentHtml: "<p>Long enough body ".repeat(30),
        contentStatus: "full",
        score: {
          overall: 80,
          dimensions: {
            importance: 81,
            usefulness: 70,
            timeliness: 78,
            depth: 60,
            technical_value: 82,
            business_value: 50,
            trend_value: 72,
          },
          tags: ["ai"],
          reason: "值得阅读。",
          summaryZh: "中文摘要",
          summaryOriginal: "English summary",
          sourceLanguage: "en",
          dimensionReasons: {
            technical_value: "技术内容明确。",
          },
          scoredAt: "2026-05-14T00:00:00.000Z",
        },
      }),
      currentLang: "zh",
      returnHref: "/?module=technical&sort=score&lang=zh&article=42",
      webSearchConfigured: true,
    }),
  );

  assert.match(html, /正文：完整/);
  assert.match(html, /评分：已评分/);
  assert.match(html, /联网补充：已配置/);
  assert.match(html, /总分/);
  assert.match(html, /维度理由/);
  assert.match(html, /技术内容明确/);
});
