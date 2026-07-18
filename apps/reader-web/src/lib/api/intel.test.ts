import assert from "node:assert/strict";
import test from "node:test";
import { researchCitationHref } from "./intel";

test("researchCitationHref carries the source quote into focus reading", () => {
  const href = researchCitationHref(42, "Chunking improves retrieval quality.");
  const url = new URL(href, "https://reader.test");

  assert.equal(url.pathname, "/read/42");
  assert.equal(url.searchParams.get("module"), "research");
  assert.equal(url.searchParams.get("quote"), "Chunking improves retrieval quality.");
});
