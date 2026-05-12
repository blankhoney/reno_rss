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
    scoredAt: row.scored_at ? new Date(row.scored_at).toISOString() : null,
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
