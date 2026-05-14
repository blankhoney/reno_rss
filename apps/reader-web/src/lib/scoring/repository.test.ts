import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_SCORING_SETTINGS,
  markReadSql,
  normalizeScoringSettingsPatch,
  setReadLaterSql,
  toArticleScore,
  updateScoringSettingsSql,
  upsertProjectQueueSql,
} from "./repository";

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

test("markReadSql upserts last_read_at without changing read_later", () => {
  const query = markReadSql({
    tenantId: "default",
    minifluxUserId: 7,
    minifluxEntryId: 42,
  });

  assert.equal(query.values[0], "default");
  assert.equal(query.values[1], 7);
  assert.equal(query.values[2], 42);
  assert.match(query.text, /last_read_at/);
  assert.match(query.text, /ON CONFLICT/);
  assert.doesNotMatch(query.text, /read_later\s*=/);
});

test("upsertProjectQueueSql deduplicates project queue entries", () => {
  const query = upsertProjectQueueSql({
    tenantId: "default",
    minifluxEntryId: 42,
    title: "Candidate",
    url: "https://example.com",
    score: 88,
    source: "manual",
  });

  assert.deepEqual(query.values, [
    "default",
    42,
    "Candidate",
    "https://example.com",
    88,
    "queued",
    "manual",
  ]);
  assert.match(query.text, /entry_project_queue/);
  assert.match(query.text, /ON CONFLICT \(tenant_id, miniflux_entry_id\)/);
});

test("normalizeScoringSettingsPatch clamps user editable values", () => {
  const patch = normalizeScoringSettingsPatch({
    autoScoreNewUnread: false,
    webhookMaxEntries: 500,
    manualRescoreEnabled: true,
  });

  assert.deepEqual(patch, {
    autoScoreNewUnread: false,
    webhookMaxEntries: 100,
    manualRescoreEnabled: true,
  });
});

test("normalizeScoringSettingsPatch defaults unknown values", () => {
  assert.deepEqual(normalizeScoringSettingsPatch({}), DEFAULT_SCORING_SETTINGS);
});

test("updateScoringSettingsSql upserts one row per tenant", () => {
  const query = updateScoringSettingsSql("default", {
    autoScoreNewUnread: false,
    webhookMaxEntries: 12,
    manualRescoreEnabled: true,
  });

  assert.deepEqual(query.values, ["default", false, 12, true]);
  assert.match(query.text, /scoring_settings/);
  assert.match(query.text, /ON CONFLICT \(tenant_id\)/);
});
