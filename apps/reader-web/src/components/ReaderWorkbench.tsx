"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Article } from "@/lib/articles/types";
import {
  filterArticlesForModule,
  filterHiddenFeedsForModule,
  resolveArticleSortId,
  resolveArticlesListModuleId,
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
import { updateArticleState } from "@/lib/api/articles";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";
import { emitToast } from "./Toast";
import { buildWorkbenchHref, normalizeCursorTrail, parseCursorTrail } from "@/lib/articles/navigation";

const ARTICLE_LIST_PAGE_SIZE = 12;
const RETURN_HIGHLIGHT_MS = 1800;

export type WorkbenchView = {
  moduleId: ModuleId | null;
  articles: Article[];
};

export function buildWorkbenchView({
  articles,
  currentModule,
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
  // Ordering is a server-side keyset contract. Re-sorting only the current
  // page would make cross-page score/dimension order incorrect.
  const visibleArticles = filterHiddenFeedsForModule(
    filterArticlesForModule(articles, moduleId),
    moduleId,
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
  initialCursorStack = [null],
}: {
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  currentQuery?: string;
  initialCursorStack?: (string | null)[];
}) {
  const initialTrail = normalizeCursorTrail(initialCursorStack);
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
  const [pageIndex, setPageIndex] = useState(() => initialTrail.length - 1);
  const [cursorStack, setCursorStack] = useState<(string | null)[]>(initialTrail);
  const [isPaging, setIsPaging] = useState(false);
  const [activeSort, setActiveSort] = useState<ArticleSortId>(currentSort);
  const [returnArticleId, setReturnArticleId] = useState<number | null>(null);
  const [highlightArticleId, setHighlightArticleId] = useState<number | null>(null);
  const lastReturnScrollKeyRef = useRef<string | null>(null);
  const initialTrailRef = useRef(initialTrail);
  const hasLoadedInitialContextRef = useRef(false);
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
  const loadPage = useCallback(async (
    cursor: string | null,
    initial = false,
    sort: ArticleSortId = activeSort,
  ) => {
    const requestSeq = pageSeqRef.current + 1;
    pageSeqRef.current = requestSeq;
    const isCurrent = () => isCurrentWorkbenchRequest(requestSeq, pageSeqRef.current);
    if (initial) {
      setIsLoading(true);
      setIsPaging(false);
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
        sort,
      });
      if (!isCurrent()) return;
      setRawArticles(page.articles);
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
      if (!initial) window.scrollTo({ top: 0 });
    } catch (loadError) {
      if (!isCurrent()) return;
      setRawArticles([]);
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
  }, [activeSort, currentModule, currentQuery]);

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

  const pushPaginationLocation = useCallback((trail: (string | null)[]) => {
    window.history.pushState(
      null,
      "",
      buildWorkbenchHref({
        module: currentModule,
        sort: activeSort,
        lang: currentLang,
        query: currentQuery,
        cursorStack: trail,
      }),
    );
  }, [activeSort, currentLang, currentModule, currentQuery]);

  const goNext = useCallback(() => {
    if (!hasMore || isPaging || nextCursor == null) return;
    const cursor = nextCursor;
    const trail = appendCursorForNextPage(cursorStack, pageIndex, cursor);
    setCursorStack(trail);
    setPageIndex(pageIndex + 1);
    pushPaginationLocation(trail);
    void loadPage(cursor);
  }, [cursorStack, hasMore, isPaging, loadPage, nextCursor, pageIndex, pushPaginationLocation]);

  const goPrev = useCallback(() => {
    if (pageIndex <= 0 || isPaging) return;
    const previousPageIndex = pageIndex - 1;
    const trail = cursorStack.slice(0, previousPageIndex + 1);
    setCursorStack(trail);
    setPageIndex(previousPageIndex);
    pushPaginationLocation(trail);
    void loadPage(cursorForPage(trail, previousPageIndex));
  }, [cursorStack, isPaging, loadPage, pageIndex, pushPaginationLocation]);

  const retryArticleList = useCallback(() => {
    void loadPage(cursorForPage(cursorStack, pageIndex), pageIndex === 0);
  }, [cursorStack, loadPage, pageIndex]);

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

    const trail = hasLoadedInitialContextRef.current ? [null] : initialTrailRef.current;
    const nextPageIndex = trail.length - 1;
    hasLoadedInitialContextRef.current = true;
    setPageIndex(nextPageIndex);
    setCursorStack(trail);
    void loadPage(cursorForPage(trail, nextPageIndex), true);
    void loadRail();
  }, [currentModule, currentQuery, loadPage, loadRail]);

  useEffect(() => {
    setActiveSort(currentSort);
  }, [currentSort]);

  useEffect(() => {
    const syncPageFromLocation = () => {
      const params = new URLSearchParams(window.location.search);
      const rawSort = params.get("sort");
      const resolution = resolveArticleSortId(rawSort != null, rawSort);
      const nextSort = resolution.ok ? resolution.sortId : "default";
      const trail = parseCursorTrail(params.get("trail"));
      const nextPageIndex = trail.length - 1;
      setActiveSort(nextSort);
      setCursorStack(trail);
      setPageIndex(nextPageIndex);
      void loadPage(cursorForPage(trail, nextPageIndex), true, nextSort);
    };
    window.addEventListener("popstate", syncPageFromLocation);
    return () => window.removeEventListener("popstate", syncPageFromLocation);
  }, [loadPage]);

  const updateSort = useCallback((nextSort: ArticleSortId) => {
    setActiveSort(nextSort);
    window.history.pushState(
      null,
      "",
      buildWorkbenchHref({
        module: currentModule,
        sort: nextSort,
        lang: currentLang,
        query: currentQuery,
      }),
    );
  }, [currentLang, currentModule, currentQuery]);

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
          currentQuery={currentQuery}
          cursorStack={cursorStack}
          highlightArticleId={highlightArticleId}
          pageIndex={pageIndex}
          hasPrev={pageIndex > 0}
          hasNext={hasMore}
          isPaging={isPaging}
          loadError={error}
          onToggleRead={(article) => {
            const nextStatus = article.status === "read" ? "unread" : "read";
            void updateArticleState(article.id, {
              status: nextStatus,
              readProgress: nextStatus === "read" ? 1 : 0,
            })
              .then(() => {
                emitToast({
                  title: nextStatus === "read" ? "已标为已读" : "已标为未读",
                  variant: "success",
                });
                window.dispatchEvent(
                  new CustomEvent(ARTICLE_DATA_CHANGED_EVENT, { detail: { articleId: article.id } }),
                );
              })
              .catch((error) => {
                emitToast({
                  title: error instanceof Error ? error.message : "更新已读状态失败",
                  variant: "error",
                });
              });
          }}
          onToggleCandidate={(article) => {
            const nextSaved = !article.starred;
            void updateArticleState(article.id, { saved: nextSaved })
              .then(() => {
                emitToast({
                  title: nextSaved ? "已加入候选" : "已移出候选",
                  variant: "success",
                });
                window.dispatchEvent(
                  new CustomEvent(ARTICLE_DATA_CHANGED_EVENT, { detail: { articleId: article.id } }),
                );
              })
              .catch((error) => {
                emitToast({
                  title: error instanceof Error ? error.message : "更新候选状态失败",
                  variant: "error",
                });
              });
          }}
          onToggleProject={(article) => {
            // Project requires candidate first (saved → project contract).
            const nextProject = !article.project;
            const body = nextProject
              ? { saved: true, project: true }
              : { project: false };
            void updateArticleState(article.id, body)
              .then(() => {
                emitToast({
                  title: nextProject ? "已立项" : "已取消立项",
                  variant: "success",
                });
                window.dispatchEvent(
                  new CustomEvent(ARTICLE_DATA_CHANGED_EVENT, { detail: { articleId: article.id } }),
                );
              })
              .catch((error) => {
                emitToast({
                  title: error instanceof Error ? error.message : "立项状态更新失败",
                  variant: "error",
                });
              });
          }}
          isLoading={isLoading}
          onPrev={goPrev}
          onNext={goNext}
          onRetry={retryArticleList}
          onSortChange={updateSort}
        />
      </div>
    </main>
  );
}
