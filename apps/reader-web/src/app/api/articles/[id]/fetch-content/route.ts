import { NextResponse } from "next/server";
import { failedArticleContentFetchResult } from "@/lib/articles/contentQuality";
import { refreshArticleOriginalContent } from "@/lib/articles/server";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idParam } = await params;
  const id = Number(idParam);
  if (!Number.isFinite(id) || id <= 0 || !Number.isInteger(id)) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  try {
    const result = await refreshArticleOriginalContent(id);
    if (!result) {
      return NextResponse.json({ error: "Article not found" }, { status: 404 });
    }
    return NextResponse.json(result);
  } catch {
    return NextResponse.json(
      { error: "fetch_content_failed", fetchResult: failedArticleContentFetchResult() },
      { status: 502 },
    );
  }
}
