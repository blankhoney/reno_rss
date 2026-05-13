import { NextResponse } from "next/server";
import {
  filterArticlesForModule,
  mergeArticleData,
  minifluxEntryFilterForModule,
  resolveArticlesListModuleId,
  sortArticlesForModule,
} from "@/lib/articles/service";
import { getConfig } from "@/lib/config";
import { MinifluxClient, parseArticlesListLimitParam } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import {
  type ArticleScore,
  getReaderStatesByEntryIds,
  getScoresByEntryIds,
} from "@/lib/scoring/repository";

export async function GET(request: Request) {
  const config = getConfig();
  const url = new URL(request.url);
  const moduleResolution = resolveArticlesListModuleId(
    url.searchParams.has("module"),
    url.searchParams.get("module"),
  );
  if (!moduleResolution.ok) {
    return NextResponse.json({ error: "Invalid module" }, { status: 400 });
  }
  const moduleId = moduleResolution.moduleId;
  const limit = parseArticlesListLimitParam(url.searchParams.get("limit"));

  const miniflux = new MinifluxClient(
    config.MINIFLUX_API_BASE_URL,
    config.MINIFLUX_USERNAME,
    config.MINIFLUX_PASSWORD,
  );
  const minifluxFilter = minifluxEntryFilterForModule(moduleId, limit);
  const baseArticles = await miniflux.getEntries(minifluxFilter);
  const entryIds = baseArticles.map((article) => article.id);
  const minifluxUserId = baseArticles[0]?.userId ?? 0;
  let scores = new Map<number, ArticleScore>();
  let states = new Map<number, { readLater: boolean; lastReadAt: string | null }>();
  try {
    const pool = getPool();
    [scores, states] = await Promise.all([
      getScoresByEntryIds(pool, config.READER_TENANT_ID, entryIds),
      getReaderStatesByEntryIds(pool, config.READER_TENANT_ID, minifluxUserId, entryIds),
    ]);
  } catch {
    scores = new Map();
    states = new Map();
  }
  const articles = sortArticlesForModule(
    filterArticlesForModule(mergeArticleData(baseArticles, scores, states), moduleId),
    moduleId,
  );

  return NextResponse.json({ articles });
}
