"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Article } from "@/lib/articles/types";
import {
  filterArticlesForModule,
  filterHiddenFeedsForModule,
  resolveArticlesListModuleId,
  sortArticlesForModule,
  type ArticleSortId,
  type ModuleId,
  type SummaryLangId,
} from "@/lib/articles/service";
import { selectedArticleIdOrFirst } from "@/lib/articles/selection";
import { getArticle, listArticles } from "@/lib/api/articles";
import {
  latestRecommendations,
  type RecommendationPage,
} from "@/lib/api/recommendations";
import { DEFAULT_SCORING_SETTINGS } from "@/lib/scoring/settings";
import { ArticleList } from "./ArticleList";
import { ArticleReader } from "./ArticleReader";
import { ModuleSidebar } from "./ModuleSidebar";
import { RecommendationList } from "./RecommendationList";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";

const ARTICLE_LIST_PAGE_SIZE = 50;

export type WorkbenchView = {
  moduleId: ModuleId | null;
  articles: Article[];
  selectedArticleId: number | null;
};

export function shouldUseHomeRecommendations(
  currentModule: string,
  currentSort: ArticleSortId,
): boolean {
  return currentModule === "all" && currentSort === "default";
}

function recommendationArticles(page: RecommendationPage | null): Article[] {
  return page?.items.flatMap((item) => (item.article ? [item.article] : [])) ?? [];
}

export function buildWorkbenchView({
  articles,
  currentModule,
  currentSort,
  requestedSelectedId,
}: {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  requestedSelectedId: number | null;
}): WorkbenchView {
  const moduleResolution = resolveArticlesListModuleId(true, currentModule);
  if (!moduleResolution.ok || moduleResolution.moduleId === "feeds") {
    return { moduleId: null, articles: [], selectedArticleId: null };
  }

  const moduleId = moduleResolution.moduleId;
  const visibleArticles = sortArticlesForModule(
    filterHiddenFeedsForModule(filterArticlesForModule(articles, moduleId), moduleId),
    moduleId,
    currentSort,
  );

  return {
    moduleId,
    articles: visibleArticles,
    selectedArticleId: selectedArticleIdOrFirst(requestedSelectedId, visibleArticles),
  };
}

export function ReaderWorkbench({
  currentModule,
  currentSort,
  currentLang,
  requestedSelectedId,
}: {
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  requestedSelectedId: number | null;
}) {
  const [rawArticles, setRawArticles] = useState<Article[]>([]);
  const [recommendationPage, setRecommendationPage] = useState<RecommendationPage | null>(null);
  const [recommendationNotice, setRecommendationNotice] = useState<{
    title: string;
    body: string;
  } | null>(null);
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const view = useMemo(
    () =>
      buildWorkbenchView({
        articles: rawArticles,
        currentModule,
        currentSort,
        requestedSelectedId,
      }),
    [currentModule, currentSort, rawArticles, requestedSelectedId],
  );
  const recommendationArticleList = useMemo(
    () => recommendationArticles(recommendationPage),
    [recommendationPage],
  );
  const showingRecommendations =
    shouldUseHomeRecommendations(currentModule, currentSort) && recommendationArticleList.length > 0;
  const selectedArticleId = showingRecommendations
    ? selectedArticleIdOrFirst(requestedSelectedId, recommendationArticleList)
    : view.selectedArticleId;

  const loadWorkbench = useCallback(async () => {
    const moduleResolution = resolveArticlesListModuleId(true, currentModule);
    if (!moduleResolution.ok || moduleResolution.moduleId === "feeds") {
      setRawArticles([]);
      setRecommendationPage(null);
      setRecommendationNotice(null);
      setSelectedArticle(null);
      setIsLoading(false);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      let nextRecommendationPage: RecommendationPage | null = null;
      let nextRecommendationNotice: { title: string; body: string } | null = null;
      let nextArticles: Article[] = [];
      let nextSelectedId: number | null = null;

      if (shouldUseHomeRecommendations(currentModule, currentSort)) {
        try {
          nextRecommendationPage = await latestRecommendations();
        } catch (recommendationError) {
          nextRecommendationNotice = {
            title: "Top10 暂不可用。",
            body:
              recommendationError instanceof Error
                ? recommendationError.message
                : "已回退到最新文章列表。",
          };
        }

        const topArticles = recommendationArticles(nextRecommendationPage);
        if (topArticles.length > 0) {
          nextArticles = topArticles;
          nextSelectedId = selectedArticleIdOrFirst(requestedSelectedId, topArticles);
        } else {
          nextRecommendationNotice = nextRecommendationNotice ?? {
            title: "Top10 尚未生成。",
            body: "需要先完成同步和评分，当前显示最新文章列表。",
          };
        }
      }

      if (nextArticles.length === 0) {
        const page = await listArticles({ limit: ARTICLE_LIST_PAGE_SIZE });
        nextArticles = page.articles;
        const nextView = buildWorkbenchView({
          articles: nextArticles,
          currentModule,
          currentSort,
          requestedSelectedId,
        });
        nextSelectedId = nextView.selectedArticleId;
      }

      const nextSelectedArticle = nextSelectedId == null ? null : await getArticle(nextSelectedId);

      setRawArticles(nextArticles);
      setRecommendationPage(nextRecommendationPage);
      setRecommendationNotice(nextRecommendationNotice);
      setSelectedArticle(nextSelectedArticle);
    } catch (loadError) {
      setRawArticles([]);
      setRecommendationPage(null);
      setRecommendationNotice(null);
      setSelectedArticle(null);
      setError(loadError instanceof Error ? loadError.message : "文章加载失败");
    } finally {
      setIsLoading(false);
    }
  }, [currentModule, currentSort, requestedSelectedId]);

  useEffect(() => {
    void loadWorkbench();
  }, [loadWorkbench]);

  useEffect(() => {
    const reload = () => void loadWorkbench();
    window.addEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
    return () => window.removeEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
  }, [loadWorkbench]);

  return (
    <main className="workbench">
      <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
      {showingRecommendations && recommendationPage ? (
        <RecommendationList
          page={recommendationPage}
          currentModule={currentModule}
          currentSort={currentSort}
          currentLang={currentLang}
          selectedArticleId={selectedArticleId}
        />
      ) : (
        <ArticleList
          articles={view.articles}
          currentModule={currentModule}
          currentSort={currentSort}
          currentLang={currentLang}
          selectedArticleId={selectedArticleId}
          initialScoringSettings={DEFAULT_SCORING_SETTINGS}
          notice={recommendationNotice ?? undefined}
        />
      )}
      {isLoading ? (
        <article className="articleReaderPane" aria-label="文章内容">
          <div className="readerEmpty">
            <p className="readerEmptyTitle">正在加载文章</p>
            <p className="readerEmptyHint">正在从 API 读取最新文章。</p>
          </div>
        </article>
      ) : error != null ? (
        <article className="articleReaderPane" aria-label="文章内容">
          <div className="readerEmpty">
            <p className="readerEmptyTitle">文章加载失败</p>
            <p className="readerEmptyHint">{error}</p>
          </div>
        </article>
      ) : (
        <ArticleReader article={selectedArticle} currentLang={currentLang} />
      )}
    </main>
  );
}
