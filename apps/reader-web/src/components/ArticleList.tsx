"use client";

import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { ScoreBadge } from "./ScoreBadge";
import { SortMenu, type SortOption } from "./SortMenu";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  selectedArticleId: number | null;
  notice?: {
    title: string;
    body: string;
  };
};

const SORT_OPTIONS: SortOption[] = [
  { id: "default", label: "默认排序" },
  { id: "latest", label: "按最新" },
  { id: "score", label: "按总分" },
  { id: "technical", label: "按技术" },
  { id: "business", label: "按商业" },
  { id: "trend", label: "按趋势" },
];

function listHref(
  currentModule: string,
  currentSort: ArticleSortId,
  currentLang: SummaryLangId,
  articleId: number,
): string {
  const qs = new URLSearchParams({
    module: currentModule,
    sort: currentSort,
    lang: currentLang,
    article: String(articleId),
  });
  return `?${qs.toString()}`;
}

function readHref(
  currentModule: string,
  currentSort: ArticleSortId,
  currentLang: SummaryLangId,
  articleId: number,
): string {
  const qs = new URLSearchParams({
    module: currentModule,
    sort: currentSort,
    lang: currentLang,
  });
  return `/read/${articleId}?${qs.toString()}`;
}

function articleSummary(article: Article, currentLang: SummaryLangId): string {
  const summary =
    currentLang === "original" ? article.summaryOriginal || article.summaryZh : article.summaryZh;
  if (summary.trim().length > 0) return summary.trim();
  return article.score ? "暂无摘要" : "未评分";
}

export function ArticleList({
  articles,
  currentModule,
  currentSort,
  currentLang,
  selectedArticleId,
  notice,
}: ArticleListProps) {
  const router = useRouter();
  const isEmpty = articles.length === 0;
  const clickTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => clearPendingPreview();
  }, []);

  function updateSort(nextSort: ArticleSortId) {
    const qs = new URLSearchParams({
      module: currentModule,
      sort: nextSort,
      lang: currentLang,
    });
    if (selectedArticleId != null) qs.set("article", String(selectedArticleId));
    router.push(`?${qs.toString()}`);
  }

  function clearPendingPreview() {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
  }

  function openPreview(href: string) {
    clearPendingPreview();
    clickTimerRef.current = window.setTimeout(() => {
      router.push(href);
      clickTimerRef.current = null;
    }, 260);
  }

  function openReader(href: string) {
    clearPendingPreview();
    router.push(href);
  }

  return (
    <section className="articleListPane" aria-label="文章列表">
      <header className="articleListHeader">
        <h1 className="articleListTitle">阅读工作台</h1>
        <div className="articleListActions">
          <SortMenu currentSort={currentSort} options={SORT_OPTIONS} onChange={updateSort} />
        </div>
      </header>
      {notice ? (
        <div className="bulkScoreStatus" role="status">
          <p>
            <strong>{notice.title}</strong> {notice.body}
          </p>
        </div>
      ) : null}
      {isEmpty ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">暂无文章</p>
          <p className="articleListEmptyHint">当前模块没有可显示的文章。</p>
        </div>
      ) : null}
      <ul className="articleList">
        {articles.map((article) => {
          const score = article.score;
          const isActive = selectedArticleId != null && selectedArticleId === article.id;
          const previewHref = listHref(currentModule, currentSort, currentLang, article.id);
          const focusHref = readHref(currentModule, currentSort, currentLang, article.id);
          return (
            <li key={article.id}>
              <article
                className={`articleCard${isActive ? " articleCardActive" : ""}`}
                role="link"
                tabIndex={0}
                aria-current={isActive ? "true" : undefined}
                aria-label={`${article.title}，单击预览，双击进入专注阅读`}
                data-preview-href={previewHref}
                data-read-href={focusHref}
                onClick={() => openPreview(previewHref)}
                onDoubleClick={() => openReader(focusHref)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") openPreview(previewHref);
                }}
              >
                <div className="articleCardMeta">
                  <span className="articleFeed">{article.feedTitle}</span>
                  {article.categoryTitle ? (
                    <span className="articleCategory">{article.categoryTitle}</span>
                  ) : null}
                </div>
                <div className="articleCardTitle">{article.title}</div>
                <p className="articleCardSummary">{articleSummary(article, currentLang)}</p>
                <div className="articleCardFooter">
                  <div className="articleCardScores">
                    <ScoreBadge label="总分" value={score?.overall ?? null} />
                    <ScoreBadge
                      label="技术"
                      value={score?.dimensions.technical_value ?? null}
                    />
                    <ScoreBadge
                      label="商业"
                      value={score?.dimensions.business_value ?? null}
                    />
                  </div>
                  <a
                    className="articleReadLink"
                    href={focusHref}
                    onClick={(event) => event.stopPropagation()}
                    onDoubleClick={(event) => event.stopPropagation()}
                  >
                    阅读
                  </a>
                </div>
              </article>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
