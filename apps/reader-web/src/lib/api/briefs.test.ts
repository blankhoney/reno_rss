import assert from "node:assert/strict";
import test from "node:test";
import {
  briefItemFromApi,
  briefTierSections,
  dailyBriefFromApi,
  isIntelligenceModule,
  latestBrief,
} from "./briefs";

function withMockFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> | Response,
): () => void {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler as typeof fetch;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

test("dailyBriefFromApi maps nested tier items and null brief", () => {
  assert.equal(dailyBriefFromApi({ brief: null }), null);

  const brief = dailyBriefFromApi({
    brief: {
      generated_at: "2026-07-18T08:00:00+00:00",
      title: "今日情报 2026-07-18",
      must_read: [
        {
          article_id: 1,
          title: "A",
          rank: 1,
          tier: "must_read",
          rank_score: 95,
          reason: "hot",
          summary_zh: "摘要",
          overall_score: 93,
        },
      ],
      worth_scan: [{ article_id: 2, title: "B", tier: "read", rank_score: 70, reason: "ok" }],
      can_skip: [{ article_id: 3, title: "C", tier: "skim", reason: "later" }],
    },
  });

  assert.ok(brief);
  assert.equal(brief.title, "今日情报 2026-07-18");
  assert.equal(brief.mustRead[0]?.summaryZh, "摘要");
  assert.equal(brief.mustRead[0]?.overallScore, 93);
  assert.equal(brief.worthScan[0]?.articleId, 2);
  assert.equal(brief.canSkip[0]?.tier, "skim");
});

test("briefItemFromApi drops rows without article_id", () => {
  assert.equal(briefItemFromApi({ title: "x" }), null);
  const item = briefItemFromApi({ article_id: 9, title: "  ", reason: null });
  assert.equal(item?.title, "文章 #9");
  assert.equal(item?.reason, "");
});

test("briefTierSections returns three labeled tiers in product order", () => {
  const sections = briefTierSections({
    generatedAt: null,
    title: "今日情报",
    mustRead: [{ articleId: 1, title: "A", rank: 1, tier: "must_read", rankScore: 90, reason: "r", summaryZh: null, overallScore: 90 }],
    worthScan: [],
    canSkip: [],
  });

  assert.deepEqual(
    sections.map((s) => s.label),
    ["今日必读", "值得扫", "可忽略"],
  );
  assert.equal(sections[0]?.items.length, 1);
});

test("isIntelligenceModule treats home/intelligence/empty as dashboard", () => {
  assert.equal(isIntelligenceModule("home"), true);
  assert.equal(isIntelligenceModule("intelligence"), true);
  assert.equal(isIntelligenceModule(""), true);
  assert.equal(isIntelligenceModule("all"), false);
});

test("latestBrief reads GET /api/briefs/latest", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  const restoreFetch = withMockFetch((input) => {
    capturedInput = input;
    return new Response(JSON.stringify({ brief: null }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });

  try {
    const brief = await latestBrief();
    assert.equal(capturedInput, "/api/briefs/latest");
    assert.equal(brief, null);
  } finally {
    restoreFetch();
  }
});
