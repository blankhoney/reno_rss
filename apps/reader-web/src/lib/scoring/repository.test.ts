import assert from "node:assert/strict";
import test from "node:test";
import { setReadLaterSql, toArticleScore } from "./repository";

test("setReadLaterSql builds an idempotent upsert", () => {
  const query = setReadLaterSql({
    tenantId: "default",
    minifluxUserId: 7,
    minifluxEntryId: 42,
    readLater: true,
  });

  assert.equal(query.values[0], "default");
  assert.equal(query.values[1], 7);
  assert.equal(query.values[2], 42);
  assert.equal(query.values[3], true);
  assert.match(query.text, /ON CONFLICT/);
  assert.match(query.text, /read_later\s*=\s*EXCLUDED\.read_later/);
});

test("toArticleScore normalizes legacy rows without dimension_scores", () => {
  const score = toArticleScore({
    score: 71,
    dimension_scores: null,
    tags: ["ai"],
    reason: "legacy",
    scored_at: "2026-05-13T00:00:00.000Z",
  });

  assert.equal(score.overall, 71);
  assert.equal(score.dimensions.technical_value, 71);
  assert.deepEqual(score.tags, ["ai"]);
});

test("toArticleScore maps invalid scored_at to null without throwing", () => {
  const score = toArticleScore({
    score: 50,
    dimension_scores: {},
    tags: [],
    reason: "",
    scored_at: "not-a-valid-date",
  });

  assert.equal(score.scoredAt, null);
});
