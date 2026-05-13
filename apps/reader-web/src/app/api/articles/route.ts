import { NextResponse } from "next/server";
import { resolveArticlesListModuleId } from "@/lib/articles/service";
import { listArticlesForModule } from "@/lib/articles/server";
import { parseArticlesListLimitParam } from "@/lib/miniflux/client";

export async function GET(request: Request) {
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
  const articles = await listArticlesForModule(moduleId, limit);

  return NextResponse.json({ articles });
}
