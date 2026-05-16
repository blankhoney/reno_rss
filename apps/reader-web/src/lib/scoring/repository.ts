import type { Pool } from "pg";
export {
  DEFAULT_SCORING_SETTINGS,
  clampInt,
  normalizeScoringSettingsPatch,
  type ScoringSettings,
} from "./settings";
import {
  DEFAULT_SCORING_SETTINGS,
  clampInt,
  normalizeScoringSettingsPatch,
  type ScoringSettings,
} from "./settings";

export type DimensionKey =
  | "importance"
  | "usefulness"
  | "timeliness"
  | "depth"
  | "technical_value"
  | "business_value"
  | "trend_value";

export type ArticleScore = {
  overall: number;
  dimensions: Record<DimensionKey, number>;
  tags: string[];
  reason: string;
  summaryZh: string;
  summaryOriginal: string;
  sourceLanguage: string;
  dimensionReasons: Partial<Record<DimensionKey, string>>;
  scoredAt: string | null;
};

export type ProjectQueueSource = "manual";

export type FeedPreference = {
  feedId: number;
  hidden: boolean;
  hiddenAt: string | null;
  updatedAt: string | null;
};

const dimensionKeys: DimensionKey[] = [
  "importance",
  "usefulness",
  "timeliness",
  "depth",
  "technical_value",
  "business_value",
  "trend_value",
];

type ScoreRow = {
  score: number;
  dimension_scores: Partial<Record<DimensionKey, number>> | null;
  tags: string[] | string | null;
  reason: string | null;
  summary_zh?: string | null;
  summary_original?: string | null;
  source_language?: string | null;
  dimension_reasons?: Partial<Record<DimensionKey, string>> | string | null;
  scored_at: string | Date | null;
};

export function toArticleScore(row: ScoreRow): ArticleScore {
  const overall = clampScore(row.score);
  const source = row.dimension_scores ?? {};
  const dimensions = Object.fromEntries(
    dimensionKeys.map((key) => [key, clampScore(source[key] ?? overall)]),
  ) as Record<DimensionKey, number>;

  return {
    overall,
    dimensions,
    tags: normalizeTags(row.tags),
    reason: row.reason ?? "",
    summaryZh: row.summary_zh ?? "",
    summaryOriginal: row.summary_original ?? "",
    sourceLanguage: row.source_language ?? "unknown",
    dimensionReasons: normalizeDimensionReasons(row.dimension_reasons),
    scoredAt: scoredAtIsoOrNull(row.scored_at),
  };
}

export function setReadLaterSql(input: {
  tenantId: string;
  minifluxUserId: number;
  minifluxEntryId: number;
  readLater: boolean;
}) {
  return {
    text: `
      INSERT INTO reader_entry_states (
        tenant_id, miniflux_user_id, miniflux_entry_id, read_later, updated_at
      )
      VALUES ($1, $2, $3, $4, NOW())
      ON CONFLICT (tenant_id, miniflux_user_id, miniflux_entry_id)
      DO UPDATE SET
        read_later = EXCLUDED.read_later,
        updated_at = NOW()
    `,
    values: [
      input.tenantId,
      input.minifluxUserId,
      input.minifluxEntryId,
      input.readLater,
    ],
  };
}

export async function upsertReadLater(
  pool: Pool,
  tenantId: string,
  minifluxUserId: number,
  minifluxEntryId: number,
  readLater: boolean,
): Promise<void> {
  const { text, values } = setReadLaterSql({
    tenantId,
    minifluxUserId,
    minifluxEntryId,
    readLater,
  });
  await pool.query(text, values);
}

export function markReadSql(input: {
  tenantId: string;
  minifluxUserId: number;
  minifluxEntryId: number;
}) {
  return {
    text: `
      INSERT INTO reader_entry_states (
        tenant_id, miniflux_user_id, miniflux_entry_id, last_read_at, updated_at
      )
      VALUES ($1, $2, $3, NOW(), NOW())
      ON CONFLICT (tenant_id, miniflux_user_id, miniflux_entry_id)
      DO UPDATE SET
        last_read_at = NOW(),
        updated_at = NOW()
    `,
    values: [input.tenantId, input.minifluxUserId, input.minifluxEntryId],
  };
}

export async function markRead(
  pool: Pool,
  tenantId: string,
  minifluxUserId: number,
  minifluxEntryId: number,
): Promise<void> {
  const { text, values } = markReadSql({ tenantId, minifluxUserId, minifluxEntryId });
  await pool.query(text, values);
}

export function upsertProjectQueueSql(input: {
  tenantId: string;
  minifluxEntryId: number;
  title: string;
  url: string;
  score: number | null;
  source: ProjectQueueSource;
}) {
  return {
    text: `
      INSERT INTO entry_project_queue (
        tenant_id, miniflux_entry_id, title, url, score, status, source, queued_at, updated_at
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
      ON CONFLICT (tenant_id, miniflux_entry_id)
      DO UPDATE SET
        title = EXCLUDED.title,
        url = EXCLUDED.url,
        score = EXCLUDED.score,
        status = EXCLUDED.status,
        source = EXCLUDED.source,
        updated_at = NOW()
    `,
    values: [
      input.tenantId,
      input.minifluxEntryId,
      input.title,
      input.url,
      input.score,
      "queued",
      input.source,
    ],
  };
}

export async function enqueueProjectEntry(
  pool: Pool,
  input: {
    tenantId: string;
    minifluxEntryId: number;
    title: string;
    url: string;
    score: number | null;
    source: ProjectQueueSource;
  },
): Promise<void> {
  const { text, values } = upsertProjectQueueSql(input);
  await pool.query(text, values);
}

export async function getProjectEntryIds(
  pool: Pool,
  tenantId: string,
  limit: number,
): Promise<number[]> {
  try {
    const result = await pool.query(
      `
        SELECT miniflux_entry_id
        FROM entry_project_queue
        WHERE tenant_id = $1
          AND status = 'queued'
        ORDER BY queued_at DESC, id DESC
        LIMIT $2
      `,
      [tenantId, limit],
    );
    return result.rows.map((row) => Number(row.miniflux_entry_id));
  } catch (error) {
    if (isUndefinedSchemaObjectError(error)) return [];
    throw error;
  }
}

export function updateFeedPreferenceSql(input: {
  tenantId: string;
  feedId: number;
  hidden: boolean;
}) {
  return {
    text: `
      INSERT INTO reader_feed_preferences (
        tenant_id, miniflux_feed_id, hidden, hidden_at, updated_at
      )
      VALUES ($1, $2, $3, CASE WHEN $3 THEN NOW() ELSE NULL END, NOW())
      ON CONFLICT (tenant_id, miniflux_feed_id)
      DO UPDATE SET
        hidden = EXCLUDED.hidden,
        hidden_at = CASE
          WHEN EXCLUDED.hidden THEN COALESCE(reader_feed_preferences.hidden_at, NOW())
          ELSE NULL
        END,
        updated_at = NOW()
      RETURNING miniflux_feed_id, hidden, hidden_at, updated_at
    `,
    values: [input.tenantId, input.feedId, input.hidden],
  };
}

export async function updateFeedPreference(
  pool: Pool,
  input: {
    tenantId: string;
    feedId: number;
    hidden: boolean;
  },
): Promise<FeedPreference> {
  const { text, values } = updateFeedPreferenceSql(input);
  const result = await pool.query(text, values);
  const row = result.rows[0];
  return {
    feedId: Number(row?.miniflux_feed_id ?? input.feedId),
    hidden: Boolean(row?.hidden ?? input.hidden),
    hiddenAt: scoredAtIsoOrNull((row?.hidden_at ?? null) as string | Date | null),
    updatedAt: scoredAtIsoOrNull((row?.updated_at ?? null) as string | Date | null),
  };
}

export async function getFeedPreferences(
  pool: Pool,
  tenantId: string,
  feedIds: number[],
): Promise<Map<number, FeedPreference>> {
  if (feedIds.length === 0) return new Map();
  try {
    const result = await pool.query(
      `
        SELECT miniflux_feed_id, hidden, hidden_at, updated_at
        FROM reader_feed_preferences
        WHERE tenant_id = $1
          AND miniflux_feed_id = ANY($2::bigint[])
      `,
      [tenantId, feedIds],
    );
    return new Map(
      result.rows.map((row) => [
        Number(row.miniflux_feed_id),
        {
          feedId: Number(row.miniflux_feed_id),
          hidden: Boolean(row.hidden),
          hiddenAt: scoredAtIsoOrNull(row.hidden_at as string | Date | null),
          updatedAt: scoredAtIsoOrNull(row.updated_at as string | Date | null),
        },
      ]),
    );
  } catch (error) {
    if (isUndefinedSchemaObjectError(error)) return new Map();
    throw error;
  }
}

export function updateScoringSettingsSql(tenantId: string, settings: ScoringSettings) {
  return {
    text: `
      INSERT INTO scoring_settings (
        tenant_id, auto_score_new_unread, webhook_max_entries,
        manual_batch_size, manual_rescore_enabled, updated_at
      )
      VALUES ($1, $2, $3, $4, $5, NOW())
      ON CONFLICT (tenant_id)
      DO UPDATE SET
        auto_score_new_unread = EXCLUDED.auto_score_new_unread,
        webhook_max_entries = EXCLUDED.webhook_max_entries,
        manual_batch_size = EXCLUDED.manual_batch_size,
        manual_rescore_enabled = EXCLUDED.manual_rescore_enabled,
        updated_at = NOW()
    `,
    values: [
      tenantId,
      settings.autoScoreNewUnread,
      settings.webhookMaxEntries,
      settings.manualBatchSize,
      settings.manualRescoreEnabled,
    ],
  };
}

export async function getScoringSettings(pool: Pool, tenantId: string): Promise<ScoringSettings> {
  let result;
  try {
    result = await pool.query(
      `
        SELECT auto_score_new_unread, webhook_max_entries, manual_rescore_enabled
             , manual_batch_size
        FROM scoring_settings
        WHERE tenant_id = $1
      `,
      [tenantId],
    );
  } catch (error) {
    if (isUndefinedSchemaObjectError(error)) return DEFAULT_SCORING_SETTINGS;
    throw error;
  }
  const row = result.rows[0];
  if (!row) return DEFAULT_SCORING_SETTINGS;
  return {
    autoScoreNewUnread: Boolean(row.auto_score_new_unread),
    webhookMaxEntries: clampInt(
      row.webhook_max_entries,
      1,
      100,
      DEFAULT_SCORING_SETTINGS.webhookMaxEntries,
    ),
    manualBatchSize: clampInt(
      row.manual_batch_size,
      1,
      50,
      DEFAULT_SCORING_SETTINGS.manualBatchSize,
    ),
    manualRescoreEnabled: Boolean(row.manual_rescore_enabled),
  };
}

export async function updateScoringSettings(
  pool: Pool,
  tenantId: string,
  settings: ScoringSettings,
): Promise<ScoringSettings> {
  const normalized = normalizeScoringSettingsPatch(settings);
  const { text, values } = updateScoringSettingsSql(tenantId, normalized);
  await pool.query(text, values);
  return normalized;
}

function scoredAtIsoOrNull(scoredAt: string | Date | null): string | null {
  if (scoredAt == null) return null;
  const date = scoredAt instanceof Date ? scoredAt : new Date(scoredAt);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function clampScore(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.min(100, Math.round(parsed)));
}

function normalizeTags(value: ScoreRow["tags"]): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function normalizeDimensionReasons(value: ScoreRow["dimension_reasons"]) {
  const parsed =
    typeof value === "string"
      ? safeJsonObject(value)
      : value !== null && typeof value === "object" && !Array.isArray(value)
        ? value
        : {};

  const reasons: Partial<Record<DimensionKey, string>> = {};
  for (const key of dimensionKeys) {
    const raw = parsed[key];
    if (typeof raw === "string" && raw.trim() !== "") {
      reasons[key] = raw.trim();
    }
  }
  return reasons;
}

function safeJsonObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function isUndefinedSchemaObjectError(error: unknown): boolean {
  return (
    error !== null &&
    typeof error === "object" &&
    "code" in error &&
    ((error as { code?: unknown }).code === "42P01" ||
      (error as { code?: unknown }).code === "42703")
  );
}

export async function getScoresByEntryIds(
  pool: Pool,
  tenantId: string,
  entryIds: number[],
): Promise<Map<number, ArticleScore>> {
  if (entryIds.length === 0) return new Map();
  const { text, values } = getScoresByEntryIdsSql(tenantId, entryIds);
  const result = await pool.query(text, values);
  return new Map(
    result.rows.map((row) => [Number(row.miniflux_entry_id), toArticleScore(row as ScoreRow)]),
  );
}

export function getScoresByEntryIdsSql(tenantId: string, entryIds: number[]) {
  return {
    text: `
      SELECT DISTINCT ON (miniflux_entry_id)
        miniflux_entry_id, score, dimension_scores, tags, reason,
        summary_zh, summary_original, source_language, dimension_reasons, scored_at
      FROM item_scores
      WHERE tenant_id = $1
        AND miniflux_entry_id = ANY($2::bigint[])
        AND scoring_status = 'success'
        AND model_provider <> 'baseline'
      ORDER BY miniflux_entry_id, scored_at DESC
    `,
    values: [tenantId, entryIds],
  };
}

export async function getReaderStatesByEntryIds(
  pool: Pool,
  tenantId: string,
  minifluxUserId: number,
  entryIds: number[],
): Promise<Map<number, { readLater: boolean; lastReadAt: string | null }>> {
  if (entryIds.length === 0) return new Map();
  const result = await pool.query(
    `
      SELECT miniflux_entry_id, read_later, last_read_at
      FROM reader_entry_states
      WHERE tenant_id = $1
        AND miniflux_user_id = $2
        AND miniflux_entry_id = ANY($3::bigint[])
    `,
    [tenantId, minifluxUserId, entryIds],
  );
  return new Map(
    result.rows.map((row) => [
      Number(row.miniflux_entry_id),
      {
        readLater: Boolean(row.read_later),
        lastReadAt: scoredAtIsoOrNull(row.last_read_at as string | Date | null),
      },
    ]),
  );
}
