import type { Pool } from "pg";

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
  scoredAt: string | null;
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

export async function getScoresByEntryIds(
  pool: Pool,
  tenantId: string,
  entryIds: number[],
): Promise<Map<number, ArticleScore>> {
  if (entryIds.length === 0) return new Map();
  const result = await pool.query(
    `
      SELECT DISTINCT ON (miniflux_entry_id)
        miniflux_entry_id, score, dimension_scores, tags, reason, scored_at
      FROM item_scores
      WHERE tenant_id = $1
        AND miniflux_entry_id = ANY($2::bigint[])
      ORDER BY miniflux_entry_id, scored_at DESC
    `,
    [tenantId, entryIds],
  );
  return new Map(
    result.rows.map((row) => [Number(row.miniflux_entry_id), toArticleScore(row as ScoreRow)]),
  );
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
