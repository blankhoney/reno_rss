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
import {
  getArticleStats,
  listArticles,
  type ArticleStats,
} from "@/lib/api/articles";
import {
  latestRecommendations,
  type RecommendationPage,
} from "@/lib/api/recommendations";
import { ArticleList } from "./ArticleList";
import { ModuleSidebar } from "./ModuleSidebar";
import { WorkbenchRail } from "./WorkbenchRail";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";

const ARTICLE_LIST_PAGE_SIZE = 12;

export type WorkbenchView = {
  moduleId: ModuleId | null;
  articles: Article[];
};

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

export function appendCursorForNextPage(
  cursorStack: (string | null)[],
  pageIndex: number,
  nextCursor: string,
): (string | null)[] {
  return [...cursorStack.slice(0, pageIndex + 1), nextCursor];
}

export function cursorForPage(
  cursorStack: (string | null)[],
  pageIndex: number,
): string | null {
  return cursorStack[pageIndex] ?? null;
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
  const [articleStats, setArticleStats] = useState<ArticleStats | null>(null);
  const [recommendationNotice, setRecommendationNotice] = useState<{
    title: string;
    body: string;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [pageIndex, setPageIndex] = useState(0);
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([null]);
  const [isPaging, setIsPaging] = useState(false);

  const view = useMemo(
    () =>
      buildWorkbenchView({
        articles: rawArticles,
        currentModule,
        currentSort,
      }),
    [currentModule, currentSort, rawArticles],
  );
  const loadPage = useCallback(async (cursor: string | null, initial = false) => {
    if (initial) {
      setIsLoading(true);
    } else {
      setIsPaging(true);
    }
    setError(null);
    try {
      const page = await listArticles({ limit: ARTICLE_LIST_PAGE_SIZE, cursor });
      setRawArticles(page.articles);
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
    } catch (loadError) {
      if (initial) setRawArticles([]);
      setNextCursor(null);
      setHasMore(false);
      setError(loadError instanceof Error ? loadError.message : "文章加载失败");
    } finally {
      if (initial) {
        setIsLoading(false);
      } else {
        setIsPaging(false);
      }
    }
  }, []);

  const loadRail = useCallback(async () => {
    const [recommendationsResult, statsResult] = await Promise.allSettled([
      latestRecommendations(),
      getArticleStats(),
    ]);
    const notices: string[] = [];

    if (recommendationsResult.status === "fulfilled") {
      setRecommendationPage(recommendationsResult.value);
    } else {
      setRecommendationPage(null);
      notices.push(
        recommendationsResult.reason instanceof Error
          ? recommendationsResult.reason.message
          : "Top10 加载失败",
      );
    }

    if (statsResult.status === "fulfilled") {
      setArticleStats(statsResult.value);
    } else {
      setArticleStats(null);
      notices.push(statsResult.reason instanceof Error ? statsResult.reason.message : "统计加载失败");
    }

    setRecommendationNotice(
      notices.length > 0
        ? {
            title: "右栏数据暂不可用。",
            body: notices.join(" "),
          }
        : null,
    );
  }, []);

  const goNext = useCallback(() => {
    if (!hasMore || isPaging || nextCursor == null) return;
    const cursor = nextCursor;
    setCursorStack((previous) => appendCursorForNextPage(previous, pageIndex, cursor));
    setPageIndex((current) => current + 1);
    void loadPage(cursor);
  }, [hasMore, isPaging, loadPage, nextCursor, pageIndex]);

  const goPrev = useCallback(() => {
    if (pageIndex <= 0 || isPaging) return;
    const previousPageIndex = pageIndex - 1;
    setPageIndex(previousPageIndex);
    void loadPage(cursorForPage(cursorStack, previousPageIndex));
  }, [cursorStack, isPaging, loadPage, pageIndex]);

  useEffect(() => {
    const moduleResolution = resolveArticlesListModuleId(true, currentModule);
    if (!moduleResolution.ok) {
      setRawArticles([]);
      setRecommendationPage(null);
      setArticleStats(null);
      setRecommendationNotice(null);
      setNextCursor(null);
      setHasMore(false);
      setPageIndex(0);
      setCursorStack([null]);
      setIsLoading(false);
      setError(null);
      return;
    }

    setPageIndex(0);
    setCursorStack([null]);
    void loadPage(null, true);
    void loadRail();
  }, [currentModule, currentSort, loadPage, loadRail]);

  useEffect(() => {
    const reload = () => {
      void loadPage(cursorForPage(cursorStack, pageIndex));
      void loadRail();
    };
    window.addEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
    return () => window.removeEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
  }, [cursorStack, loadPage, loadRail, pageIndex]);

  return (
    <main className="workbench">
      <ModuleSidebar currentModule={currentModule} currentSort={currentSort} currentLang={currentLang} />
      <ArticleList
        articles={view.articles}
        currentModule={currentModule}
        currentSort={currentSort}
        currentLang={currentLang}
        pageIndex={pageIndex}
        hasPrev={pageIndex > 0}
        hasNext={hasMore}
        isPaging={isPaging}
        onPrev={goPrev}
        onNext={goNext}
        notice={recommendationNotice ?? undefined}
      />
      <WorkbenchRail
        recommendations={recommendationPage}
        stats={articleStats}
        currentModule={currentModule}
        currentSort={currentSort}
        currentLang={currentLang}
      />
      {isLoading || error != null ? (
        <section className="workbenchStatus" aria-live="polite">
          <p className="readerEmptyTitle">{isLoading ? "正在加载文章" : "文章加载失败"}</p>
          <p className="readerEmptyHint">{isLoading ? "正在从 API 读取最新文章。" : error}</p>
        </section>
      ) : null}
    </main>
  );
}
