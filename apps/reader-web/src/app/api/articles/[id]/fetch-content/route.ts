import { NextResponse } from "next/server";
import { refreshArticleOriginalContent } from "@/lib/articles/server";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: idParam } = await params;
  const id = Number(idParam);
  if (!Number.isFinite(id) || id <= 0 || !Number.isInteger(id)) {
    return NextResponse.json({ error: "Invalid id" }, { status: 400 });
  }

  try {
    const article = await refreshArticleOriginalContent(id);
    if (!article) {
      return NextResponse.json({ error: "Article not found" }, { status: 404 });
    }
    return NextResponse.json({ article });
  } catch {
    return NextResponse.json({ error: "fetch_content_failed" }, { status: 502 });
  }
}
