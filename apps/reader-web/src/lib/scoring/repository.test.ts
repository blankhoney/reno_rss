import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_SCORING_SETTINGS,
  getScoresByEntryIdsSql,
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
    summary_zh: "中文摘要",
    summary_original: "Original summary",
    source_language: "en",
    dimension_reasons: { technical_value: "技术原因" },
    scored_at: "2026-05-13T00:00:00.000Z",
  });

  assert.equal(score.overall, 71);
  assert.equal(score.dimensions.technical_value, 71);
  assert.deepEqual(score.tags, ["ai"]);
  assert.equal(score.summaryZh, "中文摘要");
  assert.equal(score.summaryOriginal, "Original summary");
  assert.equal(score.sourceLanguage, "en");
  assert.equal(score.dimensionReasons.technical_value, "技术原因");
});

test("toArticleScore maps invalid scored_at to null without throwing", () => {
  const score = toArticleScore({
    score: 50,
    dimension_scores: {},
    tags: [],
    reason: "",
    summary_zh: "",
    summary_original: "",
    source_language: "unknown",
    dimension_reasons: {},
    scored_at: "not-a-valid-date",
  });

  assert.equal(score.scoredAt, null);
});

test("getScoresByEntryIdsSql reads only successful non-baseline scores", () => {
  const query = getScoresByEntryIdsSql("default", [1, 2]);

  assert.deepEqual(query.values, ["default", [1, 2]]);
  assert.match(query.text, /scoring_status\s*=\s*'success'/);
  assert.match(query.text, /model_provider\s*<>\s*'baseline'/);
  assert.match(query.text, /summary_zh/);
  assert.match(query.text, /dimension_reasons/);
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
    manualBatchSize: 500,
    manualRescoreEnabled: true,
  });

  assert.deepEqual(patch, {
    autoScoreNewUnread: false,
    webhookMaxEntries: 100,
    manualBatchSize: 50,
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
    manualBatchSize: 20,
    manualRescoreEnabled: true,
  });

  assert.deepEqual(query.values, ["default", false, 12, 20, true]);
  assert.match(query.text, /scoring_settings/);
  assert.match(query.text, /manual_batch_size/);
  assert.match(query.text, /ON CONFLICT \(tenant_id\)/);
});
