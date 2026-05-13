import type { Article } from "@/lib/articles/types";
import { ArticleList } from "@/components/ArticleList";
import { ArticleReader } from "@/components/ArticleReader";
import { ModuleSidebar } from "@/components/ModuleSidebar";
import { resolveArticlesListModuleId } from "@/lib/articles/service";
import { getArticleForReader, listArticlesForModule } from "@/lib/articles/server";
import { DEFAULT_ARTICLES_LIST_LIMIT } from "@/lib/miniflux/client";

function normalizeModule(raw: string | string[] | undefined): string {
  if (typeof raw === "string" && raw !== "") return raw;
  return "all";
}

function parseArticleId(raw: string | string[] | undefined): number | null {
  const v = typeof raw === "string" ? raw : undefined;
  if (!v) return null;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

async function fetchArticlesList(module: string): Promise<Article[]> {
  const moduleResolution = resolveArticlesListModuleId(true, module);
  if (!moduleResolution.ok) {
    return [];
  }
  return listArticlesForModule(moduleResolution.moduleId, DEFAULT_ARTICLES_LIST_LIMIT);
}

async function fetchArticleById(id: number): Promise<Article | null> {
  return getArticleForReader(id);
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
