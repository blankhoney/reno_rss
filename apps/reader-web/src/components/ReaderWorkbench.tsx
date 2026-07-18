"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Article } from "@/lib/articles/types";
import {
  filterArticlesForModule,
  filterHiddenFeedsForModule,
  resolveArticleSortId,
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
import { WorkbenchRibbon } from "./WorkbenchRibbon";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";

const ARTICLE_LIST_PAGE_SIZE = 12;
const RETURN_HIGHLIGHT_MS = 1800;

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

export function parseReturnArticleId(search: string): number | null {
  const params = new URLSearchParams(search);
  const raw = params.get("article");
  if (raw == null || !/^\d+$/.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

export function articleReturnSelector(articleId: number): string {
  return `[data-article-id="${articleId}"]`;
}

export function isCurrentWorkbenchRequest(requestSeq: number, latestSeq: number): boolean {
  return requestSeq === latestSeq;
}

export function ReaderWorkbench({
  currentModule,
  currentSort,
  currentLang,
  currentQuery = "",
}: {
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  currentQuery?: string;
}) {
  const [rawArticles, setRawArticles] = useState<Article[]>([]);
  const [recommendationPage, setRecommendationPage] = useState<RecommendationPage | null>(null);
  const [articleStats, setArticleStats] = useState<ArticleStats | null>(null);
  const [recommendationNotice, setRecommendationNotice] = useState<{
    title: string;
    body: string;
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRailLoading, setIsRailLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [pageIndex, setPageIndex] = useState(0);
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([null]);
  const [isPaging, setIsPaging] = useState(false);
  const [activeSort, setActiveSort] = useState<ArticleSortId>(currentSort);
  const [returnArticleId, setReturnArticleId] = useState<number | null>(null);
  const [highlightArticleId, setHighlightArticleId] = useState<number | null>(null);
  const lastReturnScrollKeyRef = useRef<string | null>(null);
  const pageSeqRef = useRef(0);
  const railSeqRef = useRef(0);

  const view = useMemo(
    () =>
      buildWorkbenchView({
        articles: rawArticles,
        currentModule,
        currentSort: activeSort,
      }),
    [activeSort, currentModule, rawArticles],
  );
  const loadPage = useCallback(async (cursor: string | null, initial = false) => {
    const requestSeq = pageSeqRef.current + 1;
    pageSeqRef.current = requestSeq;
    const isCurrent = () => isCurrentWorkbenchRequest(requestSeq, pageSeqRef.current);
    if (initial) {
      setIsLoading(true);
    } else {
      setIsPaging(true);
    }
    setError(null);
    try {
      const page = await listArticles({
        limit: ARTICLE_LIST_PAGE_SIZE,
        cursor,
        module: currentModule,
        q: currentQuery,
      });
      if (!isCurrent()) return;
      setRawArticles(page.articles);
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
      if (!initial) window.scrollTo({ top: 0 });
    } catch (loadError) {
      if (!isCurrent()) return;
      if (initial) setRawArticles([]);
      setNextCursor(null);
      setHasMore(false);
      setError(loadError instanceof Error ? loadError.message : "文章加载失败");
    } finally {
      if (!isCurrent()) return;
      if (initial) {
        setIsLoading(false);
      } else {
        setIsPaging(false);
      }
    }
  }, [currentModule, currentQuery]);

  const loadRail = useCallback(async () => {
    const requestSeq = railSeqRef.current + 1;
    railSeqRef.current = requestSeq;
    const isCurrent = () => isCurrentWorkbenchRequest(requestSeq, railSeqRef.current);
    setIsRailLoading(true);
    setRecommendationNotice(null);
    try {
      const [recommendationsResult, statsResult] = await Promise.allSettled([
        latestRecommendations(),
        getArticleStats(),
      ]);
      const notices: string[] = [];
      if (!isCurrent()) return;

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
              title: "状态数据暂不可用。",
              body: notices.join(" "),
            }
          : null,
      );
    } finally {
      if (!isCurrent()) return;
      setIsRailLoading(false);
    }
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

  const retryArticleList = useCallback(() => {
    void loadPage(cursorForPage(cursorStack, pageIndex), rawArticles.length === 0);
  }, [cursorStack, loadPage, pageIndex, rawArticles.length]);

  useEffect(() => {
    const moduleResolution = resolveArticlesListModuleId(true, currentModule);
    if (!moduleResolution.ok) {
      pageSeqRef.current += 1;
      railSeqRef.current += 1;
      setRawArticles([]);
      setRecommendationPage(null);
      setArticleStats(null);
      setRecommendationNotice(null);
      setIsRailLoading(false);
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
  }, [currentModule, currentQuery, loadPage, loadRail]);

  useEffect(() => {
    setActiveSort(currentSort);
  }, [currentSort]);

  useEffect(() => {
    const syncSortFromLocation = () => {
      const params = new URLSearchParams(window.location.search);
      const rawSort = params.get("sort");
      const resolution = resolveArticleSortId(rawSort != null, rawSort);
      setActiveSort(resolution.ok ? resolution.sortId : "default");
    };
    window.addEventListener("popstate", syncSortFromLocation);
    return () => window.removeEventListener("popstate", syncSortFromLocation);
  }, []);

  const updateSort = useCallback((nextSort: ArticleSortId) => {
    setActiveSort(nextSort);
    const qs = new URLSearchParams(window.location.search);
    qs.set("module", currentModule);
    qs.set("sort", nextSort);
    qs.set("lang", currentLang);
    window.history.pushState(null, "", `?${qs.toString()}`);
  }, [currentLang, currentModule]);

  useEffect(() => {
    const nextReturnArticleId =
      typeof window === "undefined" ? null : parseReturnArticleId(window.location.search);
    setReturnArticleId(nextReturnArticleId);
    setHighlightArticleId(nextReturnArticleId);
    lastReturnScrollKeyRef.current = null;
  }, [activeSort, currentLang, currentModule]);

  useEffect(() => {
    if (returnArticleId == null || isLoading || isPaging) return;
    if (!view.articles.some((article) => article.id === returnArticleId)) return;

    const scrollKey = `${pageIndex}:${returnArticleId}`;
    if (lastReturnScrollKeyRef.current === scrollKey) return;

    const target = document.querySelector<HTMLElement>(articleReturnSelector(returnArticleId));
    if (target == null) return;

    lastReturnScrollKeyRef.current = scrollKey;
    setHighlightArticleId(returnArticleId);
    target.scrollIntoView({ block: "center" });

    const timeout = window.setTimeout(() => {
      setHighlightArticleId((current) => (current === returnArticleId ? null : current));
    }, RETURN_HIGHLIGHT_MS);
    return () => window.clearTimeout(timeout);
  }, [isLoading, isPaging, pageIndex, returnArticleId, view.articles]);

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
      <ModuleSidebar currentModule={currentModule} currentSort={activeSort} currentLang={currentLang} />
      <div className="workbenchMain">
        <WorkbenchRibbon
          recommendations={recommendationPage}
          stats={articleStats}
          currentModule={currentModule}
          currentSort={activeSort}
          currentLang={currentLang}
          isLoading={isRailLoading}
          notice={recommendationNotice ?? undefined}
          onRetry={() => void loadRail()}
        />
        <ArticleList
          articles={view.articles}
          currentModule={currentModule}
          currentSort={activeSort}
          currentLang={currentLang}
          highlightArticleId={highlightArticleId}
          pageIndex={pageIndex}
          hasPrev={pageIndex > 0}
          hasNext={hasMore}
          isPaging={isPaging}
          isLoading={isLoading}
          onPrev={goPrev}
          onNext={goNext}
          onSortChange={updateSort}
        />
      </div>
      {error != null ? (
        <section className="workbenchStatus" aria-live="polite">
          <p className="readerEmptyTitle">文章加载失败</p>
          <p className="readerEmptyHint">{error}</p>
          <button type="button" className="readerToolbarBtn" onClick={retryArticleList}>
            重试
          </button>
        </section>
      ) : null}
    </main>
  );
}
