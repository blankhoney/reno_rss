import type { Article } from "@/lib/articles/types";
import { ArticleList } from "@/components/ArticleList";
import { ArticleReader } from "@/components/ArticleReader";
import { FeedQualityPanel } from "@/components/FeedQualityPanel";
import { ModuleSidebar } from "@/components/ModuleSidebar";
import {
  resolveArticlesListModuleId,
  resolveArticleSortId,
  resolveSummaryLangId,
  type ArticleSortId,
} from "@/lib/articles/service";
import { selectedArticleIdOrFirst } from "@/lib/articles/selection";
import { getArticleForReader, listArticlesForModule } from "@/lib/articles/server";
import { DEFAULT_ARTICLES_LIST_LIMIT } from "@/lib/miniflux/client";
import { getConfig } from "@/lib/config";
import { getPool } from "@/lib/scoring/db";
import { DEFAULT_SCORING_SETTINGS, getScoringSettings } from "@/lib/scoring/repository";

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

async function fetchArticlesList(module: string, sort: ArticleSortId): Promise<Article[]> {
  const moduleResolution = resolveArticlesListModuleId(true, module);
  if (!moduleResolution.ok) {
    return [];
  }
  return listArticlesForModule(moduleResolution.moduleId, DEFAULT_ARTICLES_LIST_LIMIT, sort);
}

async function fetchArticleById(id: number): Promise<Article | null> {
  return getArticleForReader(id);
}

async function fetchScoringSettings() {
  try {
    return await getScoringSettings(getPool(), getConfig().READER_TENANT_ID);
  } catch (error) {
    console.warn("Failed to load scoring settings for article list", error);
    return DEFAULT_SCORING_SETTINGS;
  }
}

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

export default async function HomePage({ searchParams }: PageProps) {
  const sp = (await searchParams) ?? {};
  const currentModule = normalizeModule(sp.module);
  const sortResolution = resolveArticleSortId(
    typeof sp.sort === "string",
    typeof sp.sort === "string" ? sp.sort : null,
  );
  const currentSort = sortResolution.ok ? sortResolution.sortId : "default";
  const currentLang = resolveSummaryLangId(typeof sp.lang === "string" ? sp.lang : null);
  const requestedSelectedId = parseArticleId(sp.article);

  if (currentModule === "feeds") {
    return (
      <main className="workbench feedWorkbench">
        <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
        <FeedQualityPanel />
      </main>
    );
  }

  const [articles, scoringSettings] = await Promise.all([
    fetchArticlesList(currentModule, currentSort),
    fetchScoringSettings(),
  ]);
  const selectedId = selectedArticleIdOrFirst(requestedSelectedId, articles);

  let selectedArticle: Article | null = null;
  if (selectedId != null) {
    selectedArticle = articles.find((a) => a.id === selectedId) ?? null;
    if (selectedArticle == null) {
      selectedArticle = await fetchArticleById(selectedId);
    }
  }

  return (
    <main className="workbench">
      <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
      <ArticleList
        articles={articles}
        currentModule={currentModule}
        currentSort={currentSort}
        currentLang={currentLang}
        selectedArticleId={selectedId}
        initialScoringSettings={scoringSettings}
      />
      <ArticleReader article={selectedArticle} currentLang={currentLang} />
    </main>
  );
}
