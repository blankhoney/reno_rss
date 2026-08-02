import { apiGet } from "./client";

export type ApiBriefItem = {
  article_id?: number | null;
  title?: string | null;
  rank?: number | null;
  tier?: string | null;
  rank_score?: number | null;
  reason?: string | null;
  summary_zh?: string | null;
  overall_score?: number | null;
  risk_flags?: unknown;
  source_quality?: unknown;
  content_quality?: unknown;
};

export type ApiDailyBrief = {
  generated_at?: string | null;
  title?: string | null;
  source?: string | null;
  must_read?: ApiBriefItem[];
  worth_scan?: ApiBriefItem[];
  can_skip?: ApiBriefItem[];
} | null;

export type ApiBriefResponse = {
  brief?: ApiDailyBrief;
};

export type BriefItem = {
  articleId: number;
  title: string;
  rank: number | null;
  tier: string;
  rankScore: number | null;
  reason: string;
  summaryZh: string | null;
  overallScore: number | null;
  riskFlags: string[];
  sourceQuality: number | null;
  contentQuality: string | null;
};

export type DailyBrief = {
  generatedAt: string | null;
  title: string;
  source: string | null;
  mustRead: BriefItem[];
  worthScan: BriefItem[];
  canSkip: BriefItem[];
};

export type BriefTierId = "must_read" | "worth_scan" | "can_skip";

export type BriefTierSection = {
  id: BriefTierId;
  label: string;
  items: BriefItem[];
};

const TIER_LABELS: Record<BriefTierId, string> = {
  must_read: "今日必读",
  worth_scan: "值得扫",
  can_skip: "可忽略",
};

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringOrFallback(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

export function briefItemFromApi(item: unknown): BriefItem | null {
  if (item == null || typeof item !== "object" || Array.isArray(item)) return null;
  const raw = item as ApiBriefItem;
  const articleId = numberOrNull(raw.article_id);
  if (articleId == null) return null;
  return {
    articleId,
    title: stringOrFallback(raw.title, `文章 #${articleId}`),
    rank: numberOrNull(raw.rank),
    tier: stringOrFallback(raw.tier, "pending"),
    rankScore: numberOrNull(raw.rank_score),
    reason: stringOrFallback(raw.reason, ""),
    summaryZh:
      typeof raw.summary_zh === "string" && raw.summary_zh.trim().length > 0
        ? raw.summary_zh
        : null,
    overallScore: numberOrNull(raw.overall_score),
    riskFlags: stringArray(raw.risk_flags),
    sourceQuality: numberOrNull(raw.source_quality),
    contentQuality: stringOrNull(raw.content_quality),
  };
}

function mapItems(raw: unknown): BriefItem[] {
  if (!Array.isArray(raw)) return [];
  const items: BriefItem[] = [];
  for (const entry of raw) {
    const item = briefItemFromApi(entry);
    if (item) items.push(item);
  }
  return items;
}

export function dailyBriefFromApi(payload: ApiBriefResponse): DailyBrief | null {
  const brief = payload.brief ?? null;
  if (brief == null) return null;
  return {
    generatedAt: typeof brief.generated_at === "string" ? brief.generated_at : null,
    title: stringOrFallback(brief.title, "今日情报"),
    source: stringOrNull(brief.source),
    mustRead: mapItems(brief.must_read),
    worthScan: mapItems(brief.worth_scan),
    canSkip: mapItems(brief.can_skip),
  };
}

/** Build ordered dashboard sections for the three intelligence tiers. */
export function briefTierSections(brief: DailyBrief): BriefTierSection[] {
  return [
    { id: "must_read", label: TIER_LABELS.must_read, items: brief.mustRead },
    { id: "worth_scan", label: TIER_LABELS.worth_scan, items: brief.worthScan },
    { id: "can_skip", label: TIER_LABELS.can_skip, items: brief.canSkip },
  ];
}

export function isIntelligenceModule(moduleId: string): boolean {
  return moduleId === "home" || moduleId === "intelligence" || moduleId === "";
}

export async function latestBrief(): Promise<DailyBrief | null> {
  return dailyBriefFromApi(await apiGet<ApiBriefResponse>("/api/briefs/latest"));
}
