import assert from "node:assert/strict";
import test from "node:test";
import {
  latestRecommendations,
  recommendationItemFromApi,
  recommendationsFromApi,
} from "./recommendations";

function withMockFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> | Response,
): () => void {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler as typeof fetch;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

test("recommendationsFromApi maps an edition with explainable items", () => {
  const page = recommendationsFromApi({
    edition: {
      id: 3,
      generated_at: "2026-06-25T03:00:00Z",
      edition_type: "homepage_top10",
      algorithm_version: "b4.v1",
    },
    items: [
      {
        rank: 1,
        article: {
          id: 42,
          title: "Top article",
          url: "https://example.com/top",
          feed: { id: 7, title: "Example Feed" },
          category: null,
          published_at: "2026-06-25T01:00:00Z",
          content_quality: "snippet",
          state: { status: "unread", saved: false, read_progress: 0 },
        },
        rank_score: 92.5,
        tier: "must_read",
        reason: "High score",
        source: "subscription",
        risk_flags: ["low_signal"],
        risk_uncertainty: 20,
      },
    ],
    candidates: [],
  });

  assert.equal(page.edition?.algorithmVersion, "b4.v1");
  assert.equal(page.items[0]?.rank, 1);
  assert.equal(page.items[0]?.article?.title, "Top article");
  assert.equal(page.items[0]?.rankScore, 92.5);
  assert.equal(page.items[0]?.tier, "must_read");
  assert.deepEqual(page.items[0]?.riskFlags, ["low_signal"]);
});

test("recommendationsFromApi maps an empty edition as a pending Top10 state", () => {
  const page = recommendationsFromApi({ edition: null, items: [], candidates: [] });

  assert.equal(page.edition, null);
  assert.equal(page.items.length, 0);
});

test("recommendationItemFromApi tolerates missing article payloads", () => {
  const item = recommendationItemFromApi({
    rank: 2,
    article: null,
    rank_score: null,
    tier: null,
    reason: null,
    source: "exploration",
  });

  assert.equal(item.rank, 2);
  assert.equal(item.article, null);
  assert.equal(item.rankScore, null);
  assert.equal(item.tier, "pending");
  assert.equal(item.reason, "");
});

test("latestRecommendations reads the FastAPI latest endpoint", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  const restoreFetch = withMockFetch((input) => {
    capturedInput = input;
    return new Response(
      JSON.stringify({
        edition: null,
        items: [],
        candidates: [],
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });

  try {
    const page = await latestRecommendations();

    assert.equal(capturedInput, "/api/recommendations/latest");
    assert.equal(page.edition, null);
    assert.equal(page.items.length, 0);
  } finally {
    restoreFetch();
  }
});
