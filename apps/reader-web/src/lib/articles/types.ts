export type ArticleStatus = "read" | "unread" | "skipped" | "removed";
export type ArticleContentStatus = "full" | "partial";
export type ArticleContentIssue = "rss_fragment" | "blocked_or_error_page" | "fetch_failed" | null;
export type ArticleTranslationStatus = "queued" | "running" | "succeeded" | "failed" | null;
export type RecommendationTier = "must_read" | "read" | "skim" | "skip" | string;

export const ARTICLE_FEEDBACK_TYPES = [
  "underrated",
  "overrated",
  "too_promotional",
  "low_density",
  "outdated",
  "duplicate",
  "wrong_category",
  "other",
] as const;

export type ArticleFeedbackType = (typeof ARTICLE_FEEDBACK_TYPES)[number];

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

export type ArticleFeedback = {
  userScore: number;
  feedbackType: ArticleFeedbackType;
  reason: string;
  createdAt: string | null;
  updatedAt: string | null;
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
  project: boolean;
  publishedAt: string | null;
  score: ArticleScore | null;
  myFeedback: ArticleFeedback | null;
  /** The persisted 0–1 reading position from FastAPI, when the response includes article state. */
  readProgress?: number;
  /** Compatibility flag derived from an unread article with partial persisted progress. */
  readLater: boolean;
  lastReadAt: string | null;
};
