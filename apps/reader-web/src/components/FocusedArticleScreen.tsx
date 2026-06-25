"use client";

import { useCallback, useEffect, useState } from "react";
import type { Article } from "@/lib/articles/types";
import type { SummaryLangId } from "@/lib/articles/service";
import { getArticle } from "@/lib/api/articles";
import { FocusedArticleReader } from "./FocusedArticleReader";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";

export function FocusedArticleScreen({
  articleId,
  currentLang,
  returnHref,
}: {
  articleId: number;
  currentLang: SummaryLangId;
  returnHref: string;
}) {
  const [article, setArticle] = useState<Article | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadArticle = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      setArticle(await getArticle(articleId));
    } catch (loadError) {
      setArticle(null);
      setError(loadError instanceof Error ? loadError.message : "文章加载失败");
    } finally {
      setIsLoading(false);
    }
  }, [articleId]);

  useEffect(() => {
    void loadArticle();
  }, [loadArticle]);

  useEffect(() => {
    const reload = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail : null;
      if (detail?.articleId == null || detail.articleId === articleId) {
        void loadArticle();
      }
    };
    window.addEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
    return () => window.removeEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
  }, [articleId, loadArticle]);

  if (isLoading) {
    return (
      <main className="focusReader">
        <a className="readerToolbarBtn" href={returnHref}>
          返回工作台
        </a>
        <div className="readerEmpty">
          <p className="readerEmptyTitle">正在加载文章</p>
          <p className="readerEmptyHint">正在从 API 读取文章详情。</p>
        </div>
      </main>
    );
  }

  if (error != null || article == null) {
    return (
      <main className="focusReader">
        <a className="readerToolbarBtn" href={returnHref}>
          返回工作台
        </a>
        <div className="readerEmpty">
          <p className="readerEmptyTitle">文章不存在</p>
          <p className="readerEmptyHint">{error ?? "API 没有返回这篇文章。"}</p>
        </div>
      </main>
    );
  }

  return <FocusedArticleReader article={article} currentLang={currentLang} returnHref={returnHref} />;
}
