import { NextResponse } from "next/server";
import { mergeArticleData, sortArticlesForModule, type ModuleId } from "@/lib/articles/service";
import { getConfig } from "@/lib/config";
import { MinifluxClient } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import { getReaderStatesByEntryIds, getScoresByEntryIds } from "@/lib/scoring/repository";

export async function GET(request: Request) {
  const config = getConfig();
  const url = new URL(request.url);
  const moduleId = (url.searchParams.get("module") ?? "unread") as ModuleId;
  const limit = Number(url.searchParams.get("limit") ?? 50);
  const status = moduleId === "read" ? "read" : "unread";
  const starred = moduleId === "starred" ? true : undefined;

  const miniflux = new MinifluxClient(
    config.MINIFLUX_API_BASE_URL,
    config.MINIFLUX_USERNAME,
    config.MINIFLUX_PASSWORD,
  );
  const baseArticles = await miniflux.getEntries({ status, starred, limit });
  const entryIds = baseArticles.map((article) => article.id);
  const minifluxUserId = baseArticles[0]?.userId ?? 0;
  const pool = getPool();
  const [scores, states] = await Promise.all([
    getScoresByEntryIds(pool, config.READER_TENANT_ID, entryIds),
    getReaderStatesByEntryIds(pool, config.READER_TENANT_ID, minifluxUserId, entryIds),
  ]);
  const articles = sortArticlesForModule(
    mergeArticleData(baseArticles, scores, states),
    moduleId,
  );

  return NextResponse.json({ articles });
}
