import type { ArticleScore } from "@/lib/scoring/repository";

export type ArticleStatus = "read" | "unread" | "removed";

export type Article = {
  id: number;
  userId: number;
  feedId: number | null;
  feedTitle: string;
  categoryId: number | null;
  categoryTitle: string;
  title: string;
  url: string;
  contentHtml: string;
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
