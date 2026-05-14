import type { ArticleScore } from "@/lib/scoring/repository";
import sanitizeHtml from "sanitize-html";
import type { Article } from "./types";

export const MODULE_IDS = [
  "all",
  "unread",
  "read",
  "starred",
  "project",
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

export const ARTICLE_SORT_IDS = [
  "default",
  "latest",
  "score",
  "technical",
  "business",
  "trend",
] as const;

export type ArticleSortId = (typeof ARTICLE_SORT_IDS)[number];

const ARTICLE_SORT_ID_SET: ReadonlySet<string> = new Set(ARTICLE_SORT_IDS);

export const SUMMARY_LANG_IDS = ["zh", "original"] as const;

export type SummaryLangId = (typeof SUMMARY_LANG_IDS)[number];

const SUMMARY_LANG_ID_SET: ReadonlySet<string> = new Set(SUMMARY_LANG_IDS);

export function isModuleId(value: string): value is ModuleId {
  return MODULE_ID_SET.has(value);
}

/**
 * Resolves `module` for GET /api/articles. Absent `module` defaults to `"all"`.
 * When the client sends `module` but the value is empty or unknown, returns `{ ok: false }`.
 */
export function resolveArticlesListModuleId(
  hasModuleParam: boolean,
  rawModule: string | null,
): { ok: true; moduleId: ModuleId } | { ok: false } {
  if (!hasModuleParam) {
    return { ok: true, moduleId: "all" };
  }
  if (rawModule === null || rawModule === "" || !isModuleId(rawModule)) {
    return { ok: false };
  }
  return { ok: true, moduleId: rawModule };
}

export function resolveArticleSortId(
  hasSortParam: boolean,
  rawSort: string | null,
): { ok: true; sortId: ArticleSortId } | { ok: false } {
  if (!hasSortParam) {
    return { ok: true, sortId: "default" };
  }
  if (rawSort === null || rawSort === "" || !ARTICLE_SORT_ID_SET.has(rawSort)) {
    return { ok: false };
  }
  return { ok: true, sortId: rawSort as ArticleSortId };
}

export function resolveSummaryLangId(rawLang: string | null | undefined): SummaryLangId {
  return rawLang != null && SUMMARY_LANG_ID_SET.has(rawLang) ? (rawLang as SummaryLangId) : "zh";
}

function lastReadAtSortKey(lastReadAt: string | null): number {
  if (lastReadAt == null || lastReadAt === "") return 0;
  const ms = Date.parse(lastReadAt);
  return Number.isFinite(ms) ? ms : 0;
}

function publishedAtSortKey(publishedAt: string | null): number {
  if (publishedAt == null || publishedAt === "") return 0;
  const ms = Date.parse(publishedAt);
  return Number.isFinite(ms) ? ms : 0;
}

export function sortArticlesForModule(
  articles: Article[],
  moduleId: ModuleId,
  sortId: ArticleSortId = "default",
): Article[] {
  if (sortId !== "default") {
    return [...articles].sort((a, b) => scoreForSort(b, sortId) - scoreForSort(a, sortId));
  }
  if (moduleId === "project") return articles;
  return [...articles].sort((a, b) => scoreForModule(b, moduleId) - scoreForModule(a, moduleId));
}

export type MinifluxEntryModuleFilter = {
  status: "read" | "unread" | "all";
  starred?: boolean;
  limit: number;
};

export function minifluxEntryFilterForModule(
  moduleId: ModuleId,
  limit: number,
): MinifluxEntryModuleFilter {
  if (moduleId === "all") return { status: "all", starred: undefined, limit };
  if (moduleId === "read") return { status: "read", starred: undefined, limit };
  if (moduleId === "starred") return { status: "all", starred: true, limit };
  if (moduleId === "project") return { status: "all", starred: undefined, limit };
  if (moduleId === "read-later") return { status: "all", starred: undefined, limit };
  if (
    moduleId === "technical" ||
    moduleId === "business" ||
    moduleId === "trend" ||
    moduleId === "ai" ||
    moduleId === "product" ||
    moduleId === "security"
  ) {
    return { status: "all", starred: undefined, limit };
  }
  return { status: "unread", starred: undefined, limit };
}

export function filterArticlesForModule(articles: Article[], moduleId: ModuleId): Article[] {
  if (moduleId === "read-later") return articles.filter((article) => article.readLater);
  return articles;
}

export function scoreForModule(article: Article, moduleId: ModuleId): number {
  if (moduleId === "all") {
    return publishedAtSortKey(article.publishedAt);
  }
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

function scoreForSort(article: Article, sortId: ArticleSortId): number {
  if (sortId === "default") return scoreForModule(article, "all");
  if (sortId === "latest") return publishedAtSortKey(article.publishedAt);

  const score = article.score;
  if (!score) return -1;
  if (sortId === "score") return score.overall;
  if (sortId === "technical") return score.dimensions.technical_value;
  if (sortId === "business") return score.dimensions.business_value;
  if (sortId === "trend") return score.dimensions.trend_value;
  return -1;
}

type MinifluxArticle = Omit<
  Article,
  "score" | "readLater" | "lastReadAt" | "summaryZh" | "summaryOriginal" | "sourceLanguage"
>;

export function sanitizeArticleHtml(html: string): string {
  return sanitizeHtml(html, {
    allowedTags: sanitizeHtml.defaults.allowedTags.concat(["img"]),
    allowedAttributes: {
      ...sanitizeHtml.defaults.allowedAttributes,
      a: ["href", "name", "target", "rel"],
      img: ["src", "alt", "title", "width", "height", "loading"],
    },
    allowedSchemes: ["http", "https", "mailto"],
  });
}

export function articleNeedsOriginalContentFetch(html: string): boolean {
  const text = html.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  if (text.length < 280) return true;
  return /^comments?$/i.test(text);
}

export function mergeArticleData(
  articles: MinifluxArticle[],
  scores: Map<number, ArticleScore>,
  states: Map<number, { readLater: boolean; lastReadAt: string | null }>,
): Article[] {
  return articles.map((article) => {
    const state = states.get(article.id);
    return {
      ...article,
      contentHtml: sanitizeArticleHtml(article.contentHtml),
      score: scores.get(article.id) ?? null,
      summaryZh: scores.get(article.id)?.summaryZh ?? "",
      summaryOriginal: scores.get(article.id)?.summaryOriginal ?? "",
      sourceLanguage: scores.get(article.id)?.sourceLanguage ?? "unknown",
      readLater: state?.readLater ?? false,
      lastReadAt: state?.lastReadAt ?? null,
    };
  });
}
