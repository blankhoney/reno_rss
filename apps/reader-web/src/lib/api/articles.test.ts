import assert from "node:assert/strict";
import test from "node:test";

import {
  articleFromApiDetail,
  articleFromApiItem,
  enqueueFetchContentJob,
  getJob,
  listArticles,
  pollJobUntilTerminal,
  scoreFromApi,
  terminalJobStatus,
  updateArticleState,
} from "./articles";

function withMockFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> | Response,
): () => void {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler as typeof fetch;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

function headerValue(headers: HeadersInit | undefined, name: string): string | null {
  if (!headers) return null;
  return new Headers(headers).get(name);
}

test("articleFromApiItem maps FastAPI list payloads to the Article view model", () => {
  const article = articleFromApiItem({
    id: 42,
    title: "API article",
    url: "https://example.com/post",
    feed: { id: 7, title: "Example Feed" },
    category: null,
    published_at: "2026-06-25T01:00:00Z",
    content_quality: "snippet",
    score: null,
    state: { status: "unread", saved: true, read_progress: 0.25 },
  });

  assert.equal(article.id, 42);
  assert.equal(article.feedId, 7);
  assert.equal(article.feedTitle, "Example Feed");
  assert.equal(article.contentStatus, "partial");
  assert.equal(article.contentIssue, "rss_fragment");
  assert.equal(article.starred, true);
  assert.equal(article.readLater, true);
  assert.equal(article.status, "unread");
  assert.equal(article.score, null);
});

test("scoreFromApi maps the active score payload and ignores empty ones", () => {
  assert.equal(scoreFromApi(null), null);
  assert.equal(scoreFromApi({ tier: "read" }), null);

  const score = scoreFromApi({
    overall: 82,
    tier: "read",
    dimensions: { technical_value: 70, business_value: 60 },
    dimension_reasons: { technical_value: "strong" },
    tags: ["ai", 7],
    reason: "useful",
    summary_zh: "中文摘要",
    summary_original: "Original",
    source_language: "en",
    scored_at: "2026-06-25T00:00:00Z",
  });

  assert.equal(score?.overall, 82);
  assert.equal(score?.dimensions.technical_value, 70);
  assert.equal(score?.dimensions.business_value, 60);
  assert.deepEqual(score?.tags, ["ai"]);
  assert.equal(score?.summaryZh, "中文摘要");
  assert.equal(score?.sourceLanguage, "en");
});

test("articleFromApiItem surfaces the active score and zh summary", () => {
  const article = articleFromApiItem({
    id: 50,
    title: "Scored article",
    url: "https://example.com/scored",
    feed: null,
    category: null,
    published_at: null,
    content_quality: "full",
    score: { overall: 91, tier: "must_read", dimensions: { technical_value: 88 } },
    summary_zh: "列表摘要",
    state: { status: "unread", saved: false, read_progress: 0 },
  });

  assert.equal(article.score?.overall, 91);
  assert.equal(article.score?.dimensions.technical_value, 88);
  assert.equal(article.summaryZh, "列表摘要");
});

test("articleFromApiDetail sanitizes detail HTML and maps full content", () => {
  const article = articleFromApiDetail({
    id: 43,
    title: "Detail article",
    url: "https://example.com/detail",
    feed: { id: 8, title: "Detail Feed" },
    category: { id: 2, title: "AI" },
    published_at: null,
    content_quality: "full",
    content_html: '<p>Full text</p><script>alert("x")</script>',
    content_text: "Full text",
    content_source: "readability",
    summary_original: "Original summary",
    source_language: "en",
    score: null,
    state: { status: "read", saved: false, read_progress: 1 },
    sources: [],
  });

  assert.equal(article.contentStatus, "full");
  assert.equal(article.contentIssue, null);
  assert.equal(article.contentHtml, "<p>Full text</p>");
  assert.equal(article.categoryTitle, "AI");
  assert.equal(article.summaryOriginal, "Original summary");
  assert.equal(article.sourceLanguage, "en");
});

test("articleFromApiDetail tolerates missing content fields", () => {
  const article = articleFromApiDetail({
    id: 44,
    title: "Missing content",
    url: "https://example.com/missing",
    feed: null,
    category: null,
    published_at: null,
    content_quality: null,
    score: null,
    state: { status: "skipped", saved: false, read_progress: 0 },
    sources: [],
  });

  assert.equal(article.contentHtml, "");
  assert.equal(article.contentStatus, "partial");
  assert.equal(article.contentIssue, "rss_fragment");
  assert.equal(article.status, "skipped");
});

test("pollJobUntilTerminal returns the first terminal job", async () => {
  const requests: string[] = [];
  const restoreFetch = withMockFetch((input) => {
    requests.push(String(input));
    const status = requests.length === 1 ? "running" : "failed";
    return new Response(
      JSON.stringify({
        id: 9,
        job_type: "fetch_article_content",
        status,
        progress: {},
        result: {},
        last_error: status === "failed" ? "fetch_content_failed" : null,
        created_at: "2026-06-25T00:00:00Z",
        updated_at: "2026-06-25T00:00:01Z",
        completed_at: status === "failed" ? "2026-06-25T00:00:01Z" : null,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });

  try {
    const job = await pollJobUntilTerminal(9, { intervalMs: 0, maxAttempts: 3 });

    assert.deepEqual(requests, ["/api/jobs/9", "/api/jobs/9"]);
    assert.equal(job.status, "failed");
    assert.equal(job.lastError, "fetch_content_failed");
    assert.equal(terminalJobStatus("running"), false);
  } finally {
    restoreFetch();
  }
});

test("listArticles fetches a cursor page from FastAPI", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  const restoreFetch = withMockFetch((input) => {
    capturedInput = input;
    return new Response(
      JSON.stringify({
        items: [
          {
            id: 1,
            title: "One",
            url: "https://example.com/one",
            feed: null,
            category: null,
            published_at: null,
            content_quality: "snippet",
            score: null,
            state: { status: "unread", saved: false, read_progress: 0 },
          },
        ],
        next_cursor: "next",
        has_more: true,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });

  try {
    const page = await listArticles({ limit: 1, cursor: "abc" });

    assert.equal(capturedInput, "/api/articles?limit=1&cursor=abc");
    assert.equal(page.articles[0]?.title, "One");
    assert.equal(page.nextCursor, "next");
    assert.equal(page.hasMore, true);
  } finally {
    restoreFetch();
  }
});

test("updateArticleState posts status, saved state, and read progress", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((input, init) => {
    capturedInput = input;
    capturedInit = init;
    return new Response(JSON.stringify({ state: { status: "read", saved: true, read_progress: 1 } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });

  try {
    await updateArticleState(42, { status: "read", saved: true, readProgress: 1 });

    assert.equal(capturedInput, "/api/articles/42/state");
    assert.equal(capturedInit?.method, "POST");
    assert.equal(headerValue(capturedInit?.headers, "content-type"), "application/json");
    assert.equal(capturedInit?.body, JSON.stringify({ status: "read", saved: true, read_progress: 1 }));
  } finally {
    restoreFetch();
  }
});

test("enqueueFetchContentJob and getJob use the FastAPI job endpoints", async () => {
  const requests: string[] = [];
  const restoreFetch = withMockFetch((input) => {
    requests.push(String(input));
    if (String(input) === "/api/articles/42/fetch-content") {
      return new Response(JSON.stringify({ job_id: 9, status: "queued" }), {
        status: 202,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(
      JSON.stringify({
        id: 9,
        job_type: "fetch_article_content",
        status: "succeeded",
        progress: {},
        result: { outcome: "applied", content_quality: "full" },
        last_error: null,
        created_at: "2026-06-25T00:00:00Z",
        updated_at: "2026-06-25T00:00:01Z",
        completed_at: "2026-06-25T00:00:01Z",
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });

  try {
    const created = await enqueueFetchContentJob(42);
    const job = await getJob(created.jobId);

    assert.deepEqual(requests, ["/api/articles/42/fetch-content", "/api/jobs/9"]);
    assert.equal(created.jobId, 9);
    assert.equal(job.status, "succeeded");
    assert.deepEqual(job.result, { outcome: "applied", content_quality: "full" });
    assert.equal(terminalJobStatus(job.status), true);
  } finally {
    restoreFetch();
  }
});
