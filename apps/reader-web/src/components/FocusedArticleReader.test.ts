import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
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
    contentIssue: "rss_fragment",
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

const appRouter = {
  back() {},
  forward() {},
  prefetch() {},
  push() {},
  replace() {},
  refresh() {},
};

function renderFocusedReader(articleInput: Article, returnHref: string) {
  return renderToStaticMarkup(
    React.createElement(
      AppRouterContext.Provider,
      { value: appRouter as never },
      React.createElement(FocusedArticleReader, {
        article: articleInput,
        currentLang: "zh",
        returnHref,
      }),
    ),
  );
}

test("FocusedArticleReader renders the focus reading controls and partial notice", () => {
  const html = renderFocusedReader(article(), "/?module=all&sort=default&lang=zh&article=42");

  assert.match(html, /返回工作台/);
  assert.match(html, /打开原文/);
  assert.match(html, /翻译全文/);
  assert.match(html, /刷新全文/);
  assert.doesNotMatch(html, /实时评分/);
  assert.match(html, /管理控制台创建评分批次/);
  assert.match(html, /加入候选/);
  assert.match(html, /立项/);
  assert.match(html, /标记已读/);
  assert.doesNotMatch(html, /<summary>操作<\/summary>/);
  assert.match(html, /正文：片段/);
  assert.match(html, /评分：未评分/);
  assert.match(html, /译文：未翻译/);
  assert.match(html, /当前仍只有 RSS 片段/);
  assert.match(html, /文章助手/);
  assert.match(html, /总结、要点、解释选中、行动建议/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /agentDrawerBody/);
  assert.match(html, /inert=""/);
});

test("FocusedArticleReader renders scored state and dimension reasons", () => {
  const html = renderFocusedReader(
    article({
        contentHtml: "<p>Long enough body ".repeat(30),
        contentStatus: "full",
        contentIssue: null,
        score: {
          overall: 80,
          tier: "read",
          dimensions: {
            topic_relevance: 81,
            information_density: 70,
            source_quality: 76,
            novelty: 64,
            timeliness: 78,
            actionability: 82,
            reading_cost_fit: 50,
            risk_uncertainty: 32,
          },
          tags: ["ai"],
          reason: "值得阅读。",
          summaryZh: "中文摘要",
          summaryOriginal: "English summary",
          sourceLanguage: "en",
          dimensionReasons: {
            topic_relevance: "主题明确。",
          },
          scoredAt: "2026-05-14T00:00:00.000Z",
        },
    }),
    "/?module=technical&sort=score&lang=zh&article=42",
  );

  assert.match(html, /正文：完整/);
  assert.match(html, /评分：已评分/);
  assert.match(html, /推荐/);
  assert.match(html, /总分/);
  assert.match(html, /主题相关性/);
  assert.match(html, /信息密度/);
  assert.match(html, /来源质量/);
  assert.match(html, /新颖度/);
  assert.match(html, /时效性/);
  assert.match(html, /可执行性/);
  assert.match(html, /阅读成本/);
  assert.match(html, /风险·不确定/);
  assert.match(html, /风险·不确定维度越高代表越需要谨慎/);
  assert.match(html, /维度理由/);
  assert.match(html, /主题明确/);
});
