import { headers } from "next/headers";

import type { Article } from "@/lib/articles/types";
import { ArticleList } from "@/components/ArticleList";
import { ArticleReader } from "@/components/ArticleReader";
import { ModuleSidebar } from "@/components/ModuleSidebar";

function normalizeModule(raw: string | string[] | undefined): string {
  if (typeof raw === "string" && raw !== "") return raw;
  return "unread";
}

function parseArticleId(raw: string | string[] | undefined): number | null {
  const v = typeof raw === "string" ? raw : undefined;
  if (!v) return null;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

async function resolveRequestOrigin(): Promise<string> {
  const headerList = await headers();
  const host = headerList.get("x-forwarded-host") ?? headerList.get("host");
  const proto = headerList.get("x-forwarded-proto") ?? "http";
  if (host != null && host !== "") {
    return `${proto}://${host}`;
  }
  return "http://127.0.0.1:3000";
}

async function fetchArticlesList(module: string): Promise<Article[]> {
  try {
    const origin = await resolveRequestOrigin();
    const res = await fetch(`${origin}/api/articles?module=${encodeURIComponent(module)}`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    const body = (await res.json()) as { articles?: unknown };
    const list = body.articles;
    return Array.isArray(list) ? (list as Article[]) : [];
  } catch {
    return [];
  }
}

async function fetchArticleById(id: number): Promise<Article | null> {
  try {
    const origin = await resolveRequestOrigin();
    const res = await fetch(`${origin}/api/articles/${id}`, { cache: "no-store" });
    if (!res.ok) return null;
    const body = (await res.json()) as { article?: Article | null };
    return body.article ?? null;
  } catch {
    return null;
  }
}

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function HomePage({ searchParams }: PageProps) {
  const sp = (await searchParams) ?? {};
  const currentModule = normalizeModule(sp.module);
  const selectedId = parseArticleId(sp.article);

  const articles = await fetchArticlesList(currentModule);

  let selectedArticle: Article | null = null;
  if (selectedId != null) {
    selectedArticle = articles.find((a) => a.id === selectedId) ?? null;
    if (selectedArticle == null) {
      selectedArticle = await fetchArticleById(selectedId);
    }
  }

  return (
    <main className="workbench">
      <ModuleSidebar currentModule={currentModule} />
      <ArticleList
        articles={articles}
        currentModule={currentModule}
        selectedArticleId={selectedId}
      />
      <ArticleReader article={selectedArticle} />
    </main>
  );
}
