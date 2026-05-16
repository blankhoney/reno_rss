import type { Article } from "./types";
import {
  decideFetchedArticleContent,
  type ArticleContentFetchResult,
} from "./contentQuality";
import {
  articleNeedsOriginalContentFetch,
  filterHiddenFeedsForModule,
  filterArticlesForModule,
  mergeArticleData,
  minifluxEntryFilterForModule,
  modulePreservesHiddenFeeds,
  sortArticlesForModule,
  type ArticleSortId,
  type ModuleId,
} from "./service";
import { buildFeedQualitySummaries, feedQualityMap } from "@/lib/feeds/quality";
import { getConfig } from "@/lib/config";
import { MinifluxClient } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import {
  type ArticleScore,
  type FeedPreference,
  getFeedPreferences,
  getProjectEntryIds,
  getReaderStatesByEntryIds,
  getScoresByEntryIds,
} from "@/lib/scoring/repository";

type ReaderState = { readLater: boolean; lastReadAt: string | null };
const FEED_QUALITY_SAMPLE_LIMIT = 300;
const ARTICLE_LIST_MAX_SCAN_LIMIT = 1_000;

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

type MinifluxArticle = Awaited<ReturnType<MinifluxClient["getEntries"]>>[number];

async function enrichArticlesWithLocalData(baseArticles: MinifluxArticle[]): Promise<Article[]> {
  const entryIds = baseArticles.map((article) => article.id);
  const feedIds = [
    ...new Set(baseArticles.flatMap((article) => (article.feedId == null ? [] : [article.feedId]))),
  ];

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  let preferences = new Map<number, FeedPreference>();
  try {
    const maps = await getArticleMaps(entryIds);
    scores = maps.scores;
    states = maps.states;
  } catch (error) {
    console.warn("Failed to load scoring data for article list", error);
  }
  try {
    preferences = await getFeedPreferences(getPool(), getConfig().READER_TENANT_ID, feedIds);
  } catch (error) {
    console.warn("Failed to load feed preferences for article list", error);
  }

  const merged = mergeArticleData(baseArticles, scores, states);
  const qualityByFeed = feedQualityMap(
    buildFeedQualitySummaries({
      feeds: [],
      articles: merged.slice(0, FEED_QUALITY_SAMPLE_LIMIT),
      preferences,
    }),
  );

  return merged.map((article) => {
    const preference = article.feedId == null ? undefined : preferences.get(article.feedId);
    const feedQuality = article.feedId == null ? undefined : qualityByFeed.get(article.feedId);
    return {
      ...article,
      feedHidden: preference?.hidden ?? feedQuality?.hidden ?? false,
      feedQualityScore: feedQuality?.qualityScore,
    };
  });
}

function applyModuleFiltersAndSort(
  articles: Article[],
  moduleId: ModuleId,
  sortId: ArticleSortId,
): Article[] {
  return sortArticlesForModule(
    filterHiddenFeedsForModule(filterArticlesForModule(articles, moduleId), moduleId),
    moduleId,
    sortId,
  );
}

export async function listArticlesForModule(
  moduleId: ModuleId,
  limit: number,
  sortId: ArticleSortId = "default",
): Promise<Article[]> {
  if (moduleId === "feeds") return [];
  if (moduleId === "project") {
    return listProjectArticles(limit, sortId);
  }

  const miniflux = getConfiguredMinifluxClient();
  const pageSize = Math.max(limit, FEED_QUALITY_SAMPLE_LIMIT);
  const shouldBackfillHiddenFeeds = !modulePreservesHiddenFeeds(moduleId);
  const maxScan = shouldBackfillHiddenFeeds
    ? Math.max(FEED_QUALITY_SAMPLE_LIMIT, Math.min(ARTICLE_LIST_MAX_SCAN_LIMIT, limit * 20))
    : pageSize;
  const baseArticles: MinifluxArticle[] = [];
  let visibleArticles: Article[] = [];

  for (let offset = 0; offset < maxScan; offset += pageSize) {
    const pageLimit = Math.min(pageSize, maxScan - offset);
    const page = await miniflux.getEntries({
      ...minifluxEntryFilterForModule(moduleId, pageLimit),
      offset,
    });
    baseArticles.push(...page);
    visibleArticles = applyModuleFiltersAndSort(
      await enrichArticlesWithLocalData(baseArticles),
      moduleId,
      sortId,
    );
    if (visibleArticles.length >= limit || page.length < pageLimit || !shouldBackfillHiddenFeeds) {
      break;
    }
  }

  return visibleArticles.slice(0, limit);
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
  let contentIssueOverride: Article["contentIssue"] | undefined;

  if (options.autoFetchContent !== false && articleNeedsOriginalContentFetch(article.contentHtml)) {
    contentFetchAttempted = true;
    try {
      const fetchedContent = await miniflux.fetchOriginalContent(id, true);
      const decision = decideFetchedArticleContent(article.contentHtml, fetchedContent);
      article = { ...article, contentHtml: decision.html };
      if (decision.fetchResult.outcome === "rejected") {
        contentIssueOverride = "blocked_or_error_page";
      } else if (decision.fetchResult.outcome === "unchanged") {
        contentIssueOverride = decision.fetchResult.issue;
      }
    } catch (error) {
      console.warn("Failed to fetch original content for article detail", error);
      contentIssueOverride = "fetch_failed";
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
    contentStatus: contentIssueOverride != null ? "partial" : merged.contentStatus,
    contentIssue: contentIssueOverride ?? merged.contentIssue,
    contentFetchAttempted,
  };
}

export async function refreshArticleOriginalContent(id: number): Promise<{
  article: Article;
  fetchResult: ArticleContentFetchResult;
} | null> {
  const miniflux = getConfiguredMinifluxClient();
  let article = await miniflux.getEntry(id);
  if (article == null) return null;

  const fetchedContent = await miniflux.fetchOriginalContent(id, true);
  const decision = decideFetchedArticleContent(article.contentHtml, fetchedContent);
  article = { ...article, contentHtml: decision.html };

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  try {
    ({ scores, states } = await getArticleMaps([id]));
  } catch (error) {
    console.warn("Failed to load scoring data for refreshed article detail", error);
  }

  const merged = mergeArticleData([article], scores, states)[0];
  if (!merged) return null;
  const contentIssue =
    decision.fetchResult.outcome === "rejected"
      ? "blocked_or_error_page"
      : decision.fetchResult.outcome === "unchanged"
        ? decision.fetchResult.issue
        : merged.contentIssue;
  const refreshedArticle: Article = {
    ...merged,
    contentStatus: contentIssue != null ? "partial" : merged.contentStatus,
    contentIssue,
    contentFetchAttempted: true,
  };
  return { article: refreshedArticle, fetchResult: decision.fetchResult };
}
