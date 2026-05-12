import type { ArticleScore } from "@/lib/scoring/repository";
import type { Article } from "./types";

export const MODULE_IDS = [
  "unread",
  "read",
  "starred",
  "read-later",
  "technical",
  "business",
  "trend",
  "ai",
  "product",
  "security",
] as const;

export type ModuleId = (typeof MODULE_IDS)[number];

const MODULE_ID_SET: ReadonlySet<string> = new Set(MODULE_IDS);

export function isModuleId(value: string): value is ModuleId {
  return MODULE_ID_SET.has(value);
}

/**
 * Resolves `module` for GET /api/articles. Absent `module` defaults to `"unread"`.
 * When the client sends `module` but the value is empty or unknown, returns `{ ok: false }`.
 */
export function resolveArticlesListModuleId(
  hasModuleParam: boolean,
  rawModule: string | null,
): { ok: true; moduleId: ModuleId } | { ok: false } {
  if (!hasModuleParam) {
    return { ok: true, moduleId: "unread" };
  }
  if (rawModule === null || rawModule === "" || !isModuleId(rawModule)) {
    return { ok: false };
  }
  return { ok: true, moduleId: rawModule };
}

function lastReadAtSortKey(lastReadAt: string | null): number {
  if (lastReadAt == null || lastReadAt === "") return 0;
  const ms = Date.parse(lastReadAt);
  return Number.isFinite(ms) ? ms : 0;
}

export function sortArticlesForModule(articles: Article[], moduleId: ModuleId): Article[] {
  return [...articles].sort((a, b) => scoreForModule(b, moduleId) - scoreForModule(a, moduleId));
}

export function scoreForModule(article: Article, moduleId: ModuleId): number {
  if (moduleId === "read") {
    return lastReadAtSortKey(article.lastReadAt);
  }
  const score = article.score;
  if (!score) return 0;
  switch (moduleId) {
    case "technical":
    case "ai":
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

type MinifluxArticle = Omit<Article, "score" | "readLater" | "lastReadAt">;

export function mergeArticleData(
  articles: MinifluxArticle[],
  scores: Map<number, ArticleScore>,
  states: Map<number, { readLater: boolean; lastReadAt: string | null }>,
): Article[] {
  return articles.map((article) => {
    const state = states.get(article.id);
    return {
      ...article,
      score: scores.get(article.id) ?? null,
      readLater: state?.readLater ?? false,
      lastReadAt: state?.lastReadAt ?? null,
    };
  });
}
