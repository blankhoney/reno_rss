import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_ARTICLES_LIST_LIMIT,
  MAX_ARTICLES_LIST_LIMIT,
  MINIFLUX_HTTP_CLIENT_RUNTIME,
  buildEntriesUrl,
  buildEntryUrl,
  buildFetchContentUrl,
  buildMinifluxBasicAuthorizationHeader,
  normalizeMinifluxEntry,
  MinifluxClient,
  parseArticlesListLimitParam,
} from "./client";

test("MINIFLUX_HTTP_CLIENT_RUNTIME is Node.js", () => {
  assert.equal(MINIFLUX_HTTP_CLIENT_RUNTIME, "nodejs");
});

test("buildEntriesUrl preserves base URL path prefix", () => {
  const url = buildEntriesUrl("https://host/rss/miniflux", { limit: 2, offset: 0 });

  assert.equal(
    url.toString(),
    "https://host/rss/miniflux/v1/entries?limit=2&offset=0&order=published_at&direction=desc",
  );
});

test("buildEntryUrl preserves base URL path prefix", () => {
  const url = buildEntryUrl("https://host/rss/miniflux", 888);

  assert.equal(url.toString(), "https://host/rss/miniflux/v1/entries/888");
});

test("buildEntryUrl uses root path when base has no pathname", () => {
  assert.equal(buildEntryUrl("http://miniflux:8080", 1).pathname, "/v1/entries/1");
});

test("buildFetchContentUrl uses official fetch-content endpoint", () => {
  const url = buildFetchContentUrl("https://host/rss/miniflux", 888, true);

  assert.equal(
    url.toString(),
    "https://host/rss/miniflux/v1/entries/888/fetch-content?update_content=true",
  );
});

test("parseArticlesListLimitParam defaults and clamps", () => {
  assert.equal(parseArticlesListLimitParam(null), DEFAULT_ARTICLES_LIST_LIMIT);
  assert.equal(parseArticlesListLimitParam(""), DEFAULT_ARTICLES_LIST_LIMIT);
  assert.equal(parseArticlesListLimitParam("not-a-number"), DEFAULT_ARTICLES_LIST_LIMIT);
  assert.equal(parseArticlesListLimitParam("12.5"), DEFAULT_ARTICLES_LIST_LIMIT);
  assert.equal(parseArticlesListLimitParam("1"), 1);
  assert.equal(parseArticlesListLimitParam("100"), MAX_ARTICLES_LIST_LIMIT);
  assert.equal(parseArticlesListLimitParam("101"), MAX_ARTICLES_LIST_LIMIT);
  assert.equal(parseArticlesListLimitParam("0"), 1);
  assert.equal(parseArticlesListLimitParam("-3"), 1);
});

test("toggleBookmark uses PUT /v1/entries/{id}/bookmark", async () => {
  let capturedUrl = "";
  let capturedMethod: string | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    capturedUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    capturedMethod = init?.method;
    return Promise.resolve(new Response(null, { status: 204 }));
  }) as typeof fetch;

  try {
    const client = new MinifluxClient("http://localhost:8181", "u", "p");
    await client.toggleBookmark(42);
    assert.match(capturedUrl, /\/v1\/entries\/42\/bookmark(?:\?|$)/);
    assert.equal(capturedMethod, "PUT");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("getEntry returns null on 404", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (() => Promise.resolve(new Response(null, { status: 404 }))) as typeof fetch;
  try {
    const client = new MinifluxClient("http://localhost:8181", "u", "p");
    const entry = await client.getEntry(999);
    assert.equal(entry, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fetchOriginalContent returns content from Miniflux fetch-content response", async () => {
  let capturedUrl = "";
  const originalFetch = globalThis.fetch;
  globalThis.fetch = ((input: RequestInfo | URL) => {
    capturedUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    return Promise.resolve(
      new Response(JSON.stringify({ content: "<p>Fetched article body</p>" }), { status: 200 }),
    );
  }) as typeof fetch;

  try {
    const client = new MinifluxClient("http://localhost:8181", "u", "p");
    const content = await client.fetchOriginalContent(42);
    assert.match(capturedUrl, /\/v1\/entries\/42\/fetch-content\?update_content=true$/);
    assert.equal(content, "<p>Fetched article body</p>");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("buildEntriesUrl includes status, order and pagination", () => {
  const url = buildEntriesUrl("http://miniflux:8080", {
    status: "unread",
    limit: 50,
    offset: 10,
  });

  assert.equal(
    url.toString(),
    "http://miniflux:8080/v1/entries?status=unread&limit=50&offset=10&order=published_at&direction=desc",
  );
});

test("buildMinifluxBasicAuthorizationHeader encodes RFC 7617 credential form", () => {
  assert.equal(buildMinifluxBasicAuthorizationHeader("user", "p@ss"), "Basic dXNlcjpwQHNz");
});

test("getEntries forwards AbortSignal.timeout to fetch", async () => {
  let capturedSignal: AbortSignal | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = ((_input: RequestInfo | URL, init?: RequestInit) => {
    capturedSignal = init?.signal;
    return Promise.resolve(new Response(JSON.stringify({ entries: [] }), { status: 200 }));
  }) as typeof fetch;

  try {
    const client = new MinifluxClient("http://localhost:8181", "u", "p");
    await client.getEntries({});
    assert.ok(capturedSignal instanceof AbortSignal);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("normalizeMinifluxEntry preserves reading fields", () => {
  const entry = normalizeMinifluxEntry({
    id: 42,
    user_id: 7,
    feed_id: 9,
    title: "Example",
    url: "https://example.com/post",
    content: "<p>Hello</p>",
    status: "unread",
    starred: false,
    published_at: "2026-05-13T00:00:00Z",
    feed: {
      id: 9,
      title: "Feed",
      category: { id: 3, title: "AI" },
    },
  });

  assert.equal(entry.id, 42);
  assert.equal(entry.userId, 7);
  assert.equal(entry.feedTitle, "Feed");
  assert.equal(entry.categoryTitle, "AI");
  assert.equal(entry.status, "unread");
});
