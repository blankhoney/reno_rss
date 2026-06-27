export type ArticleStatus = "read" | "unread" | "skipped" | "removed";
export type ArticleContentStatus = "full" | "partial";
export type ArticleContentIssue = "rss_fragment" | "blocked_or_error_page" | "fetch_failed" | null;
export type ArticleTranslationStatus = "queued" | "running" | "succeeded" | "failed" | null;
export type RecommendationTier = "must_read" | "read" | "skim" | "skip" | string;

export const DIMENSION_KEYS = [
  "topic_relevance",
  "information_density",
  "source_quality",
  "novelty",
  "timeliness",
  "actionability",
  "reading_cost_fit",
  "risk_uncertainty",
] as const;

export type DimensionKey = (typeof DIMENSION_KEYS)[number];
export type DimensionScores = Partial<Record<DimensionKey, number>> & Record<string, number | undefined>;
export type DimensionReasons = Partial<Record<DimensionKey, string>> & Record<string, string | undefined>;

export type ArticleScore = {
  overall: number;
  tier?: RecommendationTier;
  dimensions: DimensionScores;
  tags: string[];
  reason: string;
  summaryZh: string;
  summaryOriginal: string;
  sourceLanguage: string;
  dimensionReasons: DimensionReasons;
  scoredAt: string | null;
};

export type Article = {
  id: number;
  userId: number;
  feedId: number | null;
  feedTitle: string;
  feedHidden?: boolean;
  feedQualityScore?: number;
  categoryId: number | null;
  categoryTitle: string;
  title: string;
  url: string;
  contentHtml: string;
  contentZh?: string | null;
  contentZhStatus?: ArticleTranslationStatus;
  translatedAt?: string | null;
  contentStatus: ArticleContentStatus;
  contentIssue: ArticleContentIssue;
  contentFetchAttempted: boolean;
  summaryZh: string;
  summaryOriginal: string;
  sourceLanguage: string;
  status: ArticleStatus;
  starred: boolean;
  publishedAt: string | null;
  score: ArticleScore | null;
  readLater: boolean;
  lastReadAt: string | null;
};
