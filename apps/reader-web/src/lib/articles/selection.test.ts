import assert from "node:assert/strict";
import test from "node:test";
import { selectedArticleIdOrFirst } from "./selection";

test("selectedArticleIdOrFirst keeps explicit article id", () => {
  assert.equal(selectedArticleIdOrFirst(9, [{ id: 1 }, { id: 2 }]), 9);
});

test("selectedArticleIdOrFirst falls back to first list item", () => {
  assert.equal(selectedArticleIdOrFirst(null, [{ id: 7 }, { id: 8 }]), 7);
});

test("selectedArticleIdOrFirst returns null for empty lists", () => {
  assert.equal(selectedArticleIdOrFirst(null, []), null);
});
