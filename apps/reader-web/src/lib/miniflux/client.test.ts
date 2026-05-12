import assert from "node:assert/strict";
import test from "node:test";
import { buildEntriesUrl, normalizeMinifluxEntry } from "./client";

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
