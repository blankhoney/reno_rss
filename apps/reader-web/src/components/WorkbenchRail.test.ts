import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Article } from "@/lib/articles/types";
import type { RecommendationPage } from "@/lib/api/recommendations";
import { WorkbenchRail } from "./WorkbenchRail";

function article(id: number): Article {
  return {
    id,
    userId: 1,
    feedId: 1,
    feedTitle: "Feed",
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
    status: "unread",
    starred: false,
    publishedAt: "2026-06-25T00:00:00Z",
    score: {
      overall: 88,
      tier: "must_read",
      dimensions: {},
      tags: [],
      reason: "值得阅读",
      summaryZh: "摘要",
      summaryOriginal: "",
      sourceLanguage: "en",
      dimensionReasons: {},
      scoredAt: "2026-06-25T00:00:00Z",
    },
    readLater: false,
    lastReadAt: null,
  };
}

function renderRail(page: RecommendationPage | null) {
  return renderToStaticMarkup(
    React.createElement(WorkbenchRail, {
      recommendations: page,
      stats: { total: 12, scored: 7, unscored: 5 },
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
    }),
  );
}

test("WorkbenchRail renders Top10 links and corpus stats", () => {
  const html = renderRail({
    edition: null,
    items: [
      {
        rank: 1,
        article: article(42),
        rankScore: 92,
        tier: "must_read",
        reason: "strong",
        source: "subscription",
        riskFlags: [],
        riskUncertainty: null,
      },
    ],
  });

  assert.match(html, /Top10/);
  assert.match(html, /Article 42/);
  assert.match(html, /href="\/read\/42\?module=all&amp;sort=default&amp;lang=zh"/);
  assert.match(html, /共/);
  assert.match(html, /已评分/);
  assert.match(html, /待评分/);
  assert.match(html, /12/);
  assert.match(html, /7/);
  assert.match(html, /5/);
});

test("WorkbenchRail renders empty states", () => {
  const html = renderToStaticMarkup(
    React.createElement(WorkbenchRail, {
      recommendations: { edition: null, items: [] },
      stats: null,
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
    }),
  );

  assert.match(html, /Top10 尚未生成/);
  assert.match(html, /统计待加载/);
});
