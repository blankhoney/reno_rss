"use client";

import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { ScoreBadge } from "./ScoreBadge";
import { ArticleListSkeleton } from "./Skeleton";
import { SortMenu, type SortOption } from "./SortMenu";
import Link from "next/link";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  highlightArticleId?: number | null;
  pageIndex?: number;
  hasPrev?: boolean;
  hasNext?: boolean;
  isPaging?: boolean;
  isLoading?: boolean;
  onPrev?: () => void;
  onNext?: () => void;
  onSortChange?: (nextSort: ArticleSortId) => void;
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
  return "暂无摘要";
}

function tierLabel(tier: string | undefined): string | null {
  if (tier === "must_read") return "必读";
  if (tier === "read") return "推荐";
  if (tier === "skim") return "略读";
  if (tier === "skip") return "跳过";
  return tier ?? null;
}

export function ArticleList({
  articles,
  currentModule,
  currentSort,
  currentLang,
  highlightArticleId = null,
  pageIndex = 0,
  hasPrev = false,
  hasNext = false,
  isPaging = false,
  isLoading = false,
  onPrev,
  onNext,
  onSortChange,
  notice,
}: ArticleListProps) {
  const isEmpty = articles.length === 0;

  function updateSort(nextSort: ArticleSortId) {
    onSortChange?.(nextSort);
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
      {isLoading ? <ArticleListSkeleton count={12} /> : null}
      {!isLoading && isEmpty ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">暂无文章</p>
          <p className="articleListEmptyHint">当前模块没有可显示的文章。</p>
        </div>
      ) : null}
      {!isLoading ? (
        <ul
          className={isPaging ? "articleList articleListPaging" : "articleList"}
          aria-busy={isPaging ? "true" : undefined}
        >
          {articles.map((article) => {
            const score = article.score;
            const focusHref = readHref(currentModule, currentSort, currentLang, article.id);
            const cardClassName =
              [
                "articleCard",
                article.status === "read" ? "articleCardRead" : "",
                article.id === highlightArticleId ? "articleCardReturnTarget" : "",
              ]
                .filter(Boolean)
                .join(" ");
            return (
              <li key={article.id}>
                <Link
                  className={cardClassName}
                  href={focusHref}
                  prefetch={false}
                  aria-label={`${article.title}，进入专注阅读`}
                  data-article-id={article.id}
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
                      {score ? (
                        <>
                          <ScoreBadge label="总分" value={score.overall} />
                          <ScoreBadge label="层级" value={tierLabel(score.tier)} />
                        </>
                      ) : (
                        <ScoreBadge label="评分" value={null} />
                      )}
                    </div>
                    <span className="articleReadLink" aria-hidden="true">
                      阅读
                    </span>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
      {!isLoading && !isEmpty ? (
        <nav className="articleListPager" aria-label="翻页">
          <button
            type="button"
            className="articleListPagerBtn"
            disabled={!hasPrev || isPaging || !onPrev}
            onClick={onPrev}
          >
            ‹ 上一页
          </button>
          <span className="articleListPagerStatus" aria-live="polite">
            第 {pageIndex + 1} 页
          </span>
          <button
            type="button"
            className="articleListPagerBtn"
            disabled={!hasNext || isPaging || !onNext}
            onClick={onNext}
          >
            下一页 ›
          </button>
        </nav>
      ) : null}
    </section>
  );
}
