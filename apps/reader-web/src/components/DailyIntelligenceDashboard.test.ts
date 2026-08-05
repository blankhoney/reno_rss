import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { briefTierSections, type DailyBrief } from "@/lib/api/briefs";

// Pure presentation check for tier labels used by the dashboard (no client fetch).
test("Daily Intelligence tier sections expose product labels", () => {
  const brief: DailyBrief = {
    generatedAt: "2026-07-18T08:00:00+00:00",
    title: "今日情报 2026-07-18",
    source: "fixture",
    mustRead: [
      {
        articleId: 1,
        title: "Alpha",
        rank: 1,
        tier: "must_read",
        rankScore: 90,
        reason: "because",
        summaryZh: "摘要",
        overallScore: 88,
        riskFlags: [],
        sourceQuality: null,
        contentQuality: null,
      },
    ],
    worthScan: [],
    canSkip: [],
  };

  const sections = briefTierSections(brief);
  assert.equal(sections[0]?.label, "今日必读");
  assert.equal(sections[1]?.label, "值得扫");
  assert.equal(sections[2]?.label, "可忽略");
  assert.equal(sections[0]?.items[0]?.title, "Alpha");
});

test("Dashboard empty state markup can be composed without browser APIs", () => {
  const empty = React.createElement(
    "div",
    { className: "articleListEmpty" },
    React.createElement("p", { className: "articleListEmptyTitle" }, "今日情报尚未生成"),
  );
  const html = renderToStaticMarkup(empty);
  assert.match(html, /今日情报尚未生成/);
});
