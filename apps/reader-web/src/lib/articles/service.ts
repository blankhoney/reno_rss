import type { Article } from "./types";

export type ModuleId =
  | "unread"
  | "read"
  | "starred"
  | "read-later"
  | "technical"
  | "business"
  | "trend"
  | "ai"
  | "product"
  | "security";

export function sortArticlesForModule(articles: Article[], moduleId: ModuleId): Article[] {
  return [...articles].sort((a, b) => scoreForModule(b, moduleId) - scoreForModule(a, moduleId));
}

export function scoreForModule(article: Article, moduleId: ModuleId): number {
  const score = article.score;
  if (!score) return 0;
  switch (moduleId) {
    case "technical":
      return score.dimensions.technical_value;
    case "business":
      return score.dimensions.business_value;
    case "trend":
      return Math.round((score.dimensions.trend_value + score.dimensions.timeliness) / 2);
    case "product":
      return Math.round((score.dimensions.usefulness + score.dimensions.business_value) / 2);
    case "security":
      return Math.round((score.dimensions.importance + score.dimensions.technical_value) / 2);
    default:
      return score.overall;
  }
}
