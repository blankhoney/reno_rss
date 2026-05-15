import type { Article } from "./types";

export function selectedArticleIdOrFirst(
  explicitArticleId: number | null,
  articles: Pick<Article, "id">[],
): number | null {
  return explicitArticleId ?? articles[0]?.id ?? null;
}
