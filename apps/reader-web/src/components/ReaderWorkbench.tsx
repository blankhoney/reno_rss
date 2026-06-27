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
import { listArticles } from "@/lib/api/articles";
import {
  latestRecommendations,
  type RecommendationPage,
} from "@/lib/api/recommendations";
import { ArticleList } from "./ArticleList";
import { ModuleSidebar } from "./ModuleSidebar";
import { RecommendationList } from "./RecommendationList";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";

const ARTICLE_LIST_PAGE_SIZE = 50;

export type WorkbenchView = {
  moduleId: ModuleId | null;
  articles: Article[];
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
}: {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
}): WorkbenchView {
  const moduleResolution = resolveArticlesListModuleId(true, currentModule);
  if (!moduleResolution.ok) {
    return { moduleId: null, articles: [] };
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
  };
}

export function ReaderWorkbench({
  currentModule,
  currentSort,
  currentLang,
}: {
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
}) {
  const [rawArticles, setRawArticles] = useState<Article[]>([]);
  const [recommendationPage, setRecommendationPage] = useState<RecommendationPage | null>(null);
  const [recommendationNotice, setRecommendationNotice] = useState<{
    title: string;
    body: string;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const view = useMemo(
    () =>
      buildWorkbenchView({
        articles: rawArticles,
        currentModule,
        currentSort,
      }),
    [currentModule, currentSort, rawArticles],
  );
  const recommendationArticleList = useMemo(
    () => recommendationArticles(recommendationPage),
    [recommendationPage],
  );
  const showingRecommendations =
    shouldUseHomeRecommendations(currentModule, currentSort) && recommendationArticleList.length > 0;

  const loadWorkbench = useCallback(async () => {
    const moduleResolution = resolveArticlesListModuleId(true, currentModule);
    if (!moduleResolution.ok) {
      setRawArticles([]);
      setRecommendationPage(null);
      setRecommendationNotice(null);
      setNextCursor(null);
      setHasMore(false);
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
      let nextCursor: string | null = null;
      let nextHasMore = false;

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
        nextCursor = page.nextCursor;
        nextHasMore = page.hasMore;
      }

      setRawArticles(nextArticles);
      setRecommendationPage(nextRecommendationPage);
      setRecommendationNotice(nextRecommendationNotice);
      setNextCursor(nextCursor);
      setHasMore(nextHasMore);
    } catch (loadError) {
      setRawArticles([]);
      setRecommendationPage(null);
      setRecommendationNotice(null);
      setNextCursor(null);
      setHasMore(false);
      setError(loadError instanceof Error ? loadError.message : "文章加载失败");
    } finally {
      setIsLoading(false);
    }
  }, [currentModule, currentSort]);

  const loadMore = useCallback(async () => {
    if (!hasMore || isLoadingMore || nextCursor == null) return;
    setIsLoadingMore(true);
    try {
      const page = await listArticles({ limit: ARTICLE_LIST_PAGE_SIZE, cursor: nextCursor });
      setRawArticles((previous) => [...previous, ...page.articles]);
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
    } catch (loadMoreError) {
      setError(loadMoreError instanceof Error ? loadMoreError.message : "加载更多失败");
    } finally {
      setIsLoadingMore(false);
    }
  }, [hasMore, isLoadingMore, nextCursor]);

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
        />
      ) : (
        <ArticleList
          articles={view.articles}
          currentModule={currentModule}
          currentSort={currentSort}
          currentLang={currentLang}
          hasMore={!showingRecommendations && hasMore}
          isLoadingMore={isLoadingMore}
          onLoadMore={() => void loadMore()}
          notice={recommendationNotice ?? undefined}
        />
      )}
      {isLoading || error != null ? (
        <section className="workbenchStatus" aria-live="polite">
          <p className="readerEmptyTitle">{isLoading ? "正在加载文章" : "文章加载失败"}</p>
          <p className="readerEmptyHint">{isLoading ? "正在从 API 读取最新文章。" : error}</p>
        </section>
      ) : null}
    </main>
  );
}
