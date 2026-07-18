import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Article } from "@/lib/articles/types";
import type { RecommendationPage } from "@/lib/api/recommendations";
import { WorkbenchRibbon } from "./WorkbenchRibbon";

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
    project: false,
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
    myFeedback: null,
    readLater: false,
    lastReadAt: null,
  };
}

function renderRibbon(page: RecommendationPage | null, defaultTop10Open = false) {
  return renderToStaticMarkup(
    React.createElement(WorkbenchRibbon, {
      recommendations: page,
      stats: { total: 12, scored: 7, unscored: 5 },
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
      defaultTop10Open,
    }),
  );
}

test("WorkbenchRibbon renders corpus stats and admin link", () => {
  const html = renderRibbon({ edition: null, items: [] });

  assert.match(html, /共 12/);
  assert.match(html, /已评分 7/);
  assert.match(html, /待评分 5/);
  assert.match(html, /href="\?module=admin&amp;sort=default&amp;lang=zh"/);
  assert.match(html, /批量评分/);
});

test("WorkbenchRibbon renders notice and retry affordance", () => {
  const html = renderToStaticMarkup(
    React.createElement(WorkbenchRibbon, {
      recommendations: { edition: null, items: [] },
      stats: null,
      currentModule: "all",
      currentSort: "default",
      currentLang: "zh",
      notice: { title: "状态数据暂不可用。", body: "Top10 加载失败" },
      onRetry() {},
    }),
  );

  assert.match(html, /状态数据暂不可用/);
  assert.match(html, /Top10 加载失败/);
  assert.match(html, />重试</);
});

test("WorkbenchRibbon renders Top10 popover links and empty state", () => {
  const emptyHtml = renderRibbon({ edition: null, items: [] }, true);
  const itemsHtml = renderRibbon(
    {
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
    },
    true,
  );

  assert.match(emptyHtml, /Top10 尚未生成/);
  assert.match(itemsHtml, /aria-expanded="true"/);
  assert.match(itemsHtml, /Article 42/);
  assert.match(itemsHtml, /href="\/read\/42\?module=all&amp;sort=default&amp;lang=zh"/);
  assert.match(itemsHtml, /scoreRing46/);
});
