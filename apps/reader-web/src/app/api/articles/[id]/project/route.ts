import { NextResponse } from "next/server";
import { getArticleForReader } from "@/lib/articles/server";
import { getConfig } from "@/lib/config";
import { getPool } from "@/lib/scoring/db";
import { enqueueProjectEntry } from "@/lib/scoring/repository";

function parsePositiveIntId(raw: string): number | null {
  const id = Number(raw);
  if (!Number.isFinite(id) || !Number.isInteger(id) || id <= 0) return null;
  return id;
}

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idRaw } = await params;
  const id = parsePositiveIntId(idRaw);
  if (id === null) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  const article = await getArticleForReader(id);
  if (article == null) {
    return NextResponse.json({ error: "Article not found" }, { status: 404 });
  }
  if (!article.starred) {
    return NextResponse.json({ error: "article_not_candidate" }, { status: 409 });
  }

  const config = getConfig();
  await enqueueProjectEntry(getPool(), {
    tenantId: config.READER_TENANT_ID,
    minifluxEntryId: article.id,
    title: article.title,
    url: article.url,
    score: article.score?.overall ?? null,
    source: "manual",
  });

  return NextResponse.json({ ok: true });
}
