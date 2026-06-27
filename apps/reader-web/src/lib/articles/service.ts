import sanitizeHtml from "sanitize-html";
import { assessArticleContent } from "./contentQuality";
import type { Article, ArticleContentIssue, ArticleContentStatus, DimensionKey } from "./types";

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
    return [...articles].sort((a, b) => {
      const scoreDelta = scoreForSort(b, sortId) - scoreForSort(a, sortId);
      if (scoreDelta !== 0) return scoreDelta;
      const qualityDelta = feedQualitySortTier(b) - feedQualitySortTier(a);
      if (qualityDelta !== 0) return qualityDelta;
      return publishedAtSortKey(b.publishedAt) - publishedAtSortKey(a.publishedAt);
    });
  }
  if (moduleId === "project") return articles;
  return [...articles].sort((a, b) => {
    const qualityDelta = feedQualitySortTier(b) - feedQualitySortTier(a);
    if (qualityDelta !== 0) return qualityDelta;
    return scoreForModule(b, moduleId) - scoreForModule(a, moduleId);
  });
}

export function filterArticlesForModule(articles: Article[], moduleId: ModuleId): Article[] {
  if (moduleId === "unread") return articles.filter((article) => article.status === "unread");
  if (moduleId === "read") return articles.filter((article) => article.status === "read");
  if (moduleId === "starred") return articles.filter((article) => article.starred);
  if (moduleId === "read-later") return articles.filter((article) => article.readLater);
  return articles;
}

export function modulePreservesHiddenFeeds(moduleId: ModuleId): boolean {
  return moduleId === "starred" || moduleId === "project" || moduleId === "read-later";
}

export function filterHiddenFeedsForModule(articles: Article[], moduleId: ModuleId): Article[] {
  if (modulePreservesHiddenFeeds(moduleId)) return articles;
  return articles.filter((article) => article.feedHidden !== true);
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
      return Math.round(
        (dimensionScore(article, "topic_relevance") + dimensionScore(article, "information_density")) / 2,
      );
    case "business":
      return dimensionScore(article, "actionability");
    case "trend":
      return Math.round(
        (dimensionScore(article, "novelty") + dimensionScore(article, "timeliness")) / 2,
      );
    case "product":
      return Math.round(
        (dimensionScore(article, "actionability") + dimensionScore(article, "reading_cost_fit")) / 2,
      );
    case "security":
      return Math.round(
        (dimensionScore(article, "source_quality") + (100 - dimensionScore(article, "risk_uncertainty"))) / 2,
      );
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
  if (sortId === "technical") return dimensionScore(article, "topic_relevance");
  if (sortId === "business") return dimensionScore(article, "actionability");
  if (sortId === "trend") return dimensionScore(article, "novelty");
  return -1;
}

function dimensionScore(article: Article, key: DimensionKey): number {
  return article.score?.dimensions[key] ?? 0;
}

function feedQualitySortTier(article: Article): number {
  const score = article.feedQualityScore;
  if (score == null) return 1;
  return score < 45 ? 0 : 1;
}

function shouldOpenArticleLinkInNewTab(href: string | undefined): boolean {
  if (href == null) return false;
  try {
    const url = new URL(href);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function sanitizeArticleHtml(html: string): string {
  return sanitizeHtml(html, {
    allowedTags: sanitizeHtml.defaults.allowedTags.concat(["img"]),
    allowedAttributes: {
      ...sanitizeHtml.defaults.allowedAttributes,
      a: ["href", "name", "target", "rel"],
      img: ["src", "alt", "title", "width", "height", "loading"],
    },
    allowedSchemes: ["http", "https", "mailto"],
    nonTextTags: ["script", "style", "textarea", "option", "xmp"],
    transformTags: {
      a: (tagName, attribs) => {
        if (!shouldOpenArticleLinkInNewTab(attribs.href)) {
          return { tagName, attribs };
        }
        return {
          tagName,
          attribs: {
            ...attribs,
            target: "_blank",
            rel: "noreferrer noopener",
          },
        };
      },
    },
  });
}

export function articleNeedsOriginalContentFetch(html: string): boolean {
  return assessArticleContent(html).status === "partial";
}

export function classifyArticleContentStatus(html: string): ArticleContentStatus {
  return assessArticleContent(html).status;
}

export function classifyArticleContentIssue(html: string): ArticleContentIssue {
  return assessArticleContent(html).issue;
}
