import assert from "node:assert/strict";
import test from "node:test";
import {
  createScoringBatch,
  enqueueAdminSync,
  getScoringBatch,
  startScoringBatch,
} from "./admin";

function withMockFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> | Response,
): () => void {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler as typeof fetch;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

test("enqueueAdminSync posts a bounded Miniflux sync request", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((input, init) => {
    capturedInput = input;
    capturedInit = init;
    return new Response(JSON.stringify({ job_id: 7, job_type: "sync_miniflux_entries", status: "queued" }), {
      status: 202,
      headers: { "content-type": "application/json" },
    });
  });

  try {
    const job = await enqueueAdminSync({ limit: 50 });

    assert.equal(capturedInput, "/api/admin/sync");
    assert.equal(capturedInit?.body, JSON.stringify({ limit: 50 }));
    assert.deepEqual(job, { jobId: 7, jobType: "sync_miniflux_entries", status: "queued" });
  } finally {
    restoreFetch();
  }
});

test("createScoringBatch and startScoringBatch use the admin endpoints", async () => {
  const requests: string[] = [];
  const restoreFetch = withMockFetch((input) => {
    requests.push(String(input));
    if (String(input) === "/api/admin/scoring-batches") {
      return new Response(
        JSON.stringify({
          batch: {
            id: 3,
            name: "Today",
            status: "queued",
            trigger_type: "manual",
            candidate_window: "today",
            article_count: 2,
            created_by: "admin-id",
            created_at: "2026-06-25T00:00:00Z",
            started_at: null,
            finished_at: null,
            items: [
              { id: 1, batch_id: 3, article_id: 10, status: "queued", base_score_id: null, error: null },
              { id: 2, batch_id: 3, article_id: 11, status: "queued", base_score_id: null, error: null },
            ],
          },
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      );
    }
    return new Response(JSON.stringify({ batch_id: 3, job_id: 9, status: "queued" }), {
      status: 202,
      headers: { "content-type": "application/json" },
    });
  });

  try {
    const batch = await createScoringBatch({
      name: "Today",
      candidateWindow: "today",
      articleIds: [10, 11],
    });
    const job = await startScoringBatch(batch.id);

    assert.deepEqual(requests, ["/api/admin/scoring-batches", "/api/admin/scoring-batches/3/start"]);
    assert.equal(batch.articleCount, 2);
    assert.deepEqual(batch.items.map((item) => item.articleId), [10, 11]);
    assert.deepEqual(job, { batchId: 3, jobId: 9, status: "queued" });
  } finally {
    restoreFetch();
  }
});

test("getScoringBatch maps batch detail", async () => {
  const restoreFetch = withMockFetch(() =>
    new Response(
      JSON.stringify({
        batch: {
          id: 5,
          name: null,
          status: "running",
          trigger_type: "manual",
          candidate_window: "last_3_days",
          article_count: 1,
          created_by: "admin-id",
          created_at: "2026-06-25T00:00:00Z",
          started_at: "2026-06-25T00:00:01Z",
          finished_at: null,
          items: [{ id: 1, batch_id: 5, article_id: 12, status: "running", base_score_id: null, error: null }],
        },
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    ),
  );

  try {
    const batch = await getScoringBatch(5);

    assert.equal(batch.id, 5);
    assert.equal(batch.status, "running");
    assert.equal(batch.items[0]?.articleId, 12);
  } finally {
    restoreFetch();
  }
});
