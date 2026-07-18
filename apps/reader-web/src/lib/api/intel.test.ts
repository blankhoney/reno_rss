import assert from "node:assert/strict";
import test from "node:test";
import { researchCitationHref, savedSearchHref } from "./intel";

test("researchCitationHref carries the source quote into focus reading", () => {
  const href = researchCitationHref(42, "Chunking improves retrieval quality.");
  const url = new URL(href, "https://reader.test");

  assert.equal(url.pathname, "/read/42");
  assert.equal(url.searchParams.get("module"), "research");
  assert.equal(url.searchParams.get("quote"), "Chunking improves retrieval quality.");
});

test("savedSearchHref keeps the search route separate from article filters", () => {
  const href = savedSearchHref({
    name: "Unread agents",
    q: "agent",
    module: "unread",
    sort: "score",
  });
  const url = new URL(href, "https://reader.test");

  assert.equal(url.searchParams.get("module"), "search");
  assert.equal(url.searchParams.get("filter"), "unread");
  assert.equal(url.searchParams.get("sort"), "score");
  assert.equal(url.searchParams.get("q"), "agent");
});
