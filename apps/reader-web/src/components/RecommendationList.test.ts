import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { RecommendationList } from "./RecommendationList";
import type { RecommendationPage } from "@/lib/api/recommendations";
import type { Article } from "@/lib/articles/types";

const appRouter = {
  back() {},
  forward() {},
  prefetch() {},
  push() {},
  replace() {},
  refresh() {},
};

function article(id: number, input: Partial<Article> = {}): Article {
  return {
    id,
    userId: 1,
    feedId: 1,
    feedTitle: "Feed",
    categoryId: null,
    categoryTitle: "",
    title: input.title ?? `Article ${id}`,
    url: `https://example.com/${id}`,
    contentHtml: "",
    contentStatus: "partial",
    contentIssue: "rss_fragment",
    contentFetchAttempted: false,
    summaryZh: "",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: "unread",
    starred: false,
    publishedAt: "2026-06-25T00:00:00Z",
    score: null,
    readLater: false,
    lastReadAt: null,
  };
}

function renderRecommendationList(page: RecommendationPage) {
  return renderToStaticMarkup(
    React.createElement(
      AppRouterContext.Provider,
      { value: appRouter as never },
      React.createElement(RecommendationList, {
        page,
        currentModule: "all",
        currentSort: "default",
        currentLang: "zh",
        selectedArticleId: 42,
      }),
    ),
  );
}

test("RecommendationList renders edition metadata and explainable Top10 cards", () => {
  const html = renderRecommendationList({
    edition: {
      id: 3,
      generatedAt: "2026-06-25T03:00:00Z",
      editionType: "homepage_top10",
      algorithmVersion: "b4.v1",
    },
    items: [
      {
        rank: 1,
        article: article(42, { title: "Top article" }),
        rankScore: 92.5,
        tier: "must_read",
        reason: "High score",
        source: "subscription",
        riskFlags: ["low_signal"],
        riskUncertainty: 20,
      },
    ],
  });

  assert.match(html, /今日 Top10/);
  assert.match(html, /b4\.v1/);
  assert.match(html, /#1/);
  assert.match(html, /must_read/);
  assert.match(html, /92\.5/);
  assert.match(html, /High score/);
  assert.match(html, /low_signal/);
  assert.match(html, /data-preview-href="\?module=all&amp;sort=default&amp;lang=zh&amp;article=42"/);
});

test("RecommendationList renders an actionable pending state for empty editions", () => {
  const html = renderRecommendationList({ edition: null, items: [] });

  assert.match(html, /Top10 尚未生成/);
  assert.match(html, /同步和评分/);
  assert.match(html, /href="\?module=all&amp;sort=latest&amp;lang=zh"/);
});
