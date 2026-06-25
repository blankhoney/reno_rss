export type ArticleStatus = "read" | "unread" | "skipped" | "removed";
export type ArticleContentStatus = "full" | "partial";
export type ArticleContentIssue = "rss_fragment" | "blocked_or_error_page" | "fetch_failed" | null;
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
