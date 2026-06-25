import { apiGet } from "./client";
import { articleFromApiItem, type ApiArticleItem } from "./articles";
import type { Article } from "@/lib/articles/types";

type ApiRecommendationEdition = {
  id?: number | null;
  generated_at?: string | null;
  edition_type?: string | null;
  algorithm_version?: string | null;
} | null;

type ApiRecommendationArticle = Partial<ApiArticleItem> | null;

export type ApiRecommendationItem = {
  rank?: number | null;
  article?: ApiRecommendationArticle;
  rank_score?: number | null;
  tier?: string | null;
  reason?: string | null;
  source?: string | null;
  risk_flags?: unknown;
  risk_uncertainty?: unknown;
};

export type ApiRecommendationResponse = {
  edition?: ApiRecommendationEdition;
  items?: ApiRecommendationItem[];
  candidates?: unknown[];
};

export type RecommendationEdition = {
  id: number | null;
  generatedAt: string | null;
  editionType: string;
  algorithmVersion: string;
};

export type RecommendationItem = {
  rank: number;
  article: Article | null;
  rankScore: number | null;
  tier: string;
  reason: string;
  source: string;
  riskFlags: string[];
  riskUncertainty: number | null;
};

export type RecommendationPage = {
  edition: RecommendationEdition | null;
  items: RecommendationItem[];
};

function stringOrFallback(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim().length > 0 ? value : fallback;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function articleFromRecommendationPayload(article: ApiRecommendationArticle): Article | null {
  if (article == null || typeof article.id !== "number" || !Number.isFinite(article.id)) {
    return null;
  }
  return articleFromApiItem({
    id: article.id,
    title: stringOrFallback(article.title, "Untitled article"),
    url: stringOrFallback(article.url, "#"),
    feed: article.feed,
    category: article.category,
    published_at: article.published_at,
    content_quality: article.content_quality,
    score: article.score,
    state: article.state,
  });
}

export function recommendationItemFromApi(item: ApiRecommendationItem): RecommendationItem {
  return {
    rank: numberOrNull(item.rank) ?? 0,
    article: articleFromRecommendationPayload(item.article ?? null),
    rankScore: numberOrNull(item.rank_score),
    tier: stringOrFallback(item.tier, "pending"),
    reason: stringOrFallback(item.reason, ""),
    source: stringOrFallback(item.source, "unknown"),
    riskFlags: stringArray(item.risk_flags),
    riskUncertainty: numberOrNull(item.risk_uncertainty),
  };
}

export function recommendationsFromApi(payload: ApiRecommendationResponse): RecommendationPage {
  const edition = payload.edition
    ? {
        id: numberOrNull(payload.edition.id),
        generatedAt: payload.edition.generated_at ?? null,
        editionType: stringOrFallback(payload.edition.edition_type, "homepage_top10"),
        algorithmVersion: stringOrFallback(payload.edition.algorithm_version, "unknown"),
      }
    : null;

  return {
    edition,
    items: (payload.items ?? []).map(recommendationItemFromApi),
  };
}

export async function latestRecommendations(): Promise<RecommendationPage> {
  return recommendationsFromApi(await apiGet<ApiRecommendationResponse>("/api/recommendations/latest"));
}
