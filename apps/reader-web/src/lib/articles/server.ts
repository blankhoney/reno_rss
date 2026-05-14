import type { Article } from "./types";
import {
  articleNeedsOriginalContentFetch,
  classifyArticleContentStatus,
  filterArticlesForModule,
  mergeArticleData,
  minifluxEntryFilterForModule,
  sortArticlesForModule,
  type ArticleSortId,
  type ModuleId,
} from "./service";
import { getConfig } from "@/lib/config";
import { MinifluxClient } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import {
  type ArticleScore,
  getProjectEntryIds,
  getReaderStatesByEntryIds,
  getScoresByEntryIds,
} from "@/lib/scoring/repository";

type ReaderState = { readLater: boolean; lastReadAt: string | null };

function getConfiguredMinifluxClient() {
  const config = getConfig();
  return new MinifluxClient(
    config.MINIFLUX_API_BASE_URL,
    config.MINIFLUX_USERNAME,
    config.MINIFLUX_PASSWORD,
  );
}

async function getArticleMaps(entryIds: number[]): Promise<{
  scores: Map<number, ArticleScore>;
  states: Map<number, ReaderState>;
}> {
  if (entryIds.length === 0) {
    return { scores: new Map(), states: new Map() };
  }

  const config = getConfig();
  const pool = getPool();
  const [scores, states] = await Promise.all([
    getScoresByEntryIds(pool, config.READER_TENANT_ID, entryIds),
    getReaderStatesByEntryIds(
      pool,
      config.READER_TENANT_ID,
      config.READER_MINIFLUX_USER_ID,
      entryIds,
    ),
  ]);
  return { scores, states };
}

export async function listArticlesForModule(
  moduleId: ModuleId,
  limit: number,
  sortId: ArticleSortId = "default",
): Promise<Article[]> {
  if (moduleId === "project") {
    return listProjectArticles(limit, sortId);
  }

  const miniflux = getConfiguredMinifluxClient();
  const baseArticles = await miniflux.getEntries(minifluxEntryFilterForModule(moduleId, limit));
  const entryIds = baseArticles.map((article) => article.id);

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  try {
    ({ scores, states } = await getArticleMaps(entryIds));
  } catch (error) {
    console.warn("Failed to load scoring data for article list", error);
    scores = new Map();
    states = new Map();
  }

  return sortArticlesForModule(
    filterArticlesForModule(mergeArticleData(baseArticles, scores, states), moduleId),
    moduleId,
    sortId,
  );
}

async function listProjectArticles(limit: number, sortId: ArticleSortId): Promise<Article[]> {
  const config = getConfig();
  const pool = getPool();
  const entryIds = await getProjectEntryIds(pool, config.READER_TENANT_ID, limit);
  if (entryIds.length === 0) return [];

  const miniflux = getConfiguredMinifluxClient();
  const baseArticles = (
    await Promise.all(entryIds.map((entryId) => miniflux.getEntry(entryId)))
  ).filter((article) => article != null);
  const ids = baseArticles.map((article) => article.id);

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  try {
    ({ scores, states } = await getArticleMaps(ids));
  } catch (error) {
    console.warn("Failed to load scoring data for project article list", error);
  }

  return sortArticlesForModule(mergeArticleData(baseArticles, scores, states), "project", sortId);
}

type ArticleReaderOptions = {
  autoFetchContent?: boolean;
};

export async function getArticleForReader(
  id: number,
  options: ArticleReaderOptions = {},
): Promise<Article | null> {
  const miniflux = getConfiguredMinifluxClient();
  let article = await miniflux.getEntry(id);
  if (article == null) return null;
  let contentFetchAttempted = false;

  if (options.autoFetchContent !== false && articleNeedsOriginalContentFetch(article.contentHtml)) {
    contentFetchAttempted = true;
    try {
      const fetchedContent = await miniflux.fetchOriginalContent(id, true);
      if (fetchedContent.trim().length > article.contentHtml.trim().length) {
        article = { ...article, contentHtml: fetchedContent };
      }
    } catch (error) {
      console.warn("Failed to fetch original content for article detail", error);
    }
  }

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  try {
    ({ scores, states } = await getArticleMaps([id]));
  } catch (error) {
    console.warn("Failed to load scoring data for article detail", error);
    scores = new Map();
    states = new Map();
  }

  const merged = mergeArticleData([article], scores, states)[0];
  if (!merged) return null;
  return {
    ...merged,
    contentStatus: classifyArticleContentStatus(merged.contentHtml),
    contentFetchAttempted,
  };
}

export async function refreshArticleOriginalContent(id: number): Promise<Article | null> {
  const miniflux = getConfiguredMinifluxClient();
  let article = await miniflux.getEntry(id);
  if (article == null) return null;

  const fetchedContent = await miniflux.fetchOriginalContent(id, true);
  if (fetchedContent.trim().length > 0) {
    article = { ...article, contentHtml: fetchedContent };
  }

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  try {
    ({ scores, states } = await getArticleMaps([id]));
  } catch (error) {
    console.warn("Failed to load scoring data for refreshed article detail", error);
  }

  const merged = mergeArticleData([article], scores, states)[0];
  if (!merged) return null;
  return {
    ...merged,
    contentStatus: classifyArticleContentStatus(merged.contentHtml),
    contentFetchAttempted: true,
  };
}
