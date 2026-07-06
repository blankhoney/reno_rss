"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { Article } from "@/lib/articles/types";
import type { SummaryLangId } from "@/lib/articles/service";
import { getArticle } from "@/lib/api/articles";
import { FocusedArticleReader } from "./FocusedArticleReader";
import { FocusedArticleSkeleton } from "./Skeleton";
import { emitToast } from "./Toast";
import { ARTICLE_DATA_CHANGED_EVENT } from "./useArticleActions";

export function shouldReloadForArticleChange(detail: unknown, articleId: number): boolean {
  const changedArticleId =
    detail != null && typeof detail === "object"
      ? (detail as { articleId?: unknown }).articleId
      : undefined;
  return changedArticleId == null || changedArticleId === articleId;
}

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
  const articleRef = useRef<Article | null>(null);
  const requestSeqRef = useRef(0);

  const loadArticle = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    const silent = mode === "refresh" && articleRef.current != null;
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    if (!silent) {
      setIsLoading(true);
      setError(null);
    }
    try {
      const nextArticle = await getArticle(articleId);
      if (requestSeqRef.current !== requestSeq) return;
      articleRef.current = nextArticle;
      setArticle(nextArticle);
      setError(null);
    } catch (loadError) {
      if (requestSeqRef.current !== requestSeq) return;
      if (silent) {
        emitToast({ title: "内容刷新失败，仍显示旧内容", variant: "error" });
        return;
      }
      articleRef.current = null;
      setArticle(null);
      setError(loadError instanceof Error ? loadError.message : "文章加载失败");
    } finally {
      if (requestSeqRef.current === requestSeq && !silent) {
        setIsLoading(false);
      }
    }
  }, [articleId]);

  useEffect(() => {
    void loadArticle("initial");
  }, [loadArticle]);

  useEffect(() => {
    const reload = (event: Event) => {
      const detail = event instanceof CustomEvent ? event.detail : null;
      if (shouldReloadForArticleChange(detail, articleId)) {
        void loadArticle("refresh");
      }
    };
    window.addEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
    return () => window.removeEventListener(ARTICLE_DATA_CHANGED_EVENT, reload);
  }, [articleId, loadArticle]);

  if (isLoading) {
    return <FocusedArticleSkeleton returnHref={returnHref} />;
  }

  if (error != null || article == null) {
    return (
      <main className="focusReader">
        <Link className="readerToolbarBtn" href={returnHref} prefetch={false}>
          返回工作台
        </Link>
        <div className="readerEmpty">
          <p className="readerEmptyTitle">文章不存在</p>
          <p className="readerEmptyHint">{error ?? "API 没有返回这篇文章。"}</p>
        </div>
      </main>
    );
  }

  return <FocusedArticleReader article={article} currentLang={currentLang} returnHref={returnHref} />;
}
