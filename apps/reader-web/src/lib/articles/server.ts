import type { Article } from "./types";
import {
  filterArticlesForModule,
  mergeArticleData,
  minifluxEntryFilterForModule,
  sortArticlesForModule,
  type ModuleId,
} from "./service";
import { getConfig } from "@/lib/config";
import { MinifluxClient } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import {
  type ArticleScore,
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

export async function listArticlesForModule(moduleId: ModuleId, limit: number): Promise<Article[]> {
  const miniflux = getConfiguredMinifluxClient();
  const baseArticles = await miniflux.getEntries(minifluxEntryFilterForModule(moduleId, limit));
  const entryIds = baseArticles.map((article) => article.id);

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  try {
    ({ scores, states } = await getArticleMaps(entryIds));
  } catch {
    scores = new Map();
    states = new Map();
  }

  return sortArticlesForModule(
    filterArticlesForModule(mergeArticleData(baseArticles, scores, states), moduleId),
    moduleId,
  );
}

export async function getArticleForReader(id: number): Promise<Article | null> {
  const miniflux = getConfiguredMinifluxClient();
  const article = await miniflux.getEntry(id);
  if (article == null) return null;

  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, ReaderState>();
  try {
    ({ scores, states } = await getArticleMaps([id]));
  } catch {
    scores = new Map();
    states = new Map();
  }

  return mergeArticleData([article], scores, states)[0] ?? null;
}
