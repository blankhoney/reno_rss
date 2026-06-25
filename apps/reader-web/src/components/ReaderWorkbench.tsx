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
import { DEFAULT_SCORING_SETTINGS } from "@/lib/scoring/settings";
import { ArticleList } from "./ArticleList";
import { ArticleReader } from "./ArticleReader";
import { ModuleSidebar } from "./ModuleSidebar";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";

const ARTICLE_LIST_PAGE_SIZE = 50;

export type WorkbenchView = {
  moduleId: ModuleId | null;
  articles: Article[];
  selectedArticleId: number | null;
};

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

  const loadWorkbench = useCallback(async () => {
    const moduleResolution = resolveArticlesListModuleId(true, currentModule);
    if (!moduleResolution.ok || moduleResolution.moduleId === "feeds") {
      setRawArticles([]);
      setSelectedArticle(null);
      setIsLoading(false);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const page = await listArticles({ limit: ARTICLE_LIST_PAGE_SIZE });
      const nextView = buildWorkbenchView({
        articles: page.articles,
        currentModule,
        currentSort,
        requestedSelectedId,
      });
      const nextSelectedArticle =
        nextView.selectedArticleId == null ? null : await getArticle(nextView.selectedArticleId);

      setRawArticles(page.articles);
      setSelectedArticle(nextSelectedArticle);
    } catch (loadError) {
      setRawArticles([]);
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
      <ArticleList
        articles={view.articles}
        currentModule={currentModule}
        currentSort={currentSort}
        currentLang={currentLang}
        selectedArticleId={view.selectedArticleId}
        initialScoringSettings={DEFAULT_SCORING_SETTINGS}
      />
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
