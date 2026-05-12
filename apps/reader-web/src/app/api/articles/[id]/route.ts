import { NextResponse } from "next/server";
import { mergeArticleData } from "@/lib/articles/service";
import { getConfig } from "@/lib/config";
import { MinifluxClient } from "@/lib/miniflux/client";
import { getPool } from "@/lib/scoring/db";
import { getReaderStatesByEntryIds, getScoresByEntryIds } from "@/lib/scoring/repository";

const DETAIL_ENTRY_FETCH_LIMIT = 500;

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idParam } = await params;
  const id = Number(idParam);
  if (!Number.isFinite(id) || id <= 0 || !Number.isInteger(id)) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  const config = getConfig();
  const miniflux = new MinifluxClient(
    config.MINIFLUX_API_BASE_URL,
    config.MINIFLUX_USERNAME,
    config.MINIFLUX_PASSWORD,
  );

  const baseArticles = await miniflux.getEntries({
    status: "all",
    limit: DETAIL_ENTRY_FETCH_LIMIT,
  });
  const article = baseArticles.find((a) => a.id === id);
  if (!article) {
    return NextResponse.json({ error: "Article not found" }, { status: 404 });
  }

  const pool = getPool();
  const minifluxUserId = article.userId;
  const [scores, states] = await Promise.all([
    getScoresByEntryIds(pool, config.READER_TENANT_ID, [id]),
    getReaderStatesByEntryIds(pool, config.READER_TENANT_ID, minifluxUserId, [id]),
  ]);
  const [merged] = mergeArticleData([article], scores, states);
  return NextResponse.json({ article: merged });
}
