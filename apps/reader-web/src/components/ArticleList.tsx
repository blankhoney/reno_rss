"use client";

import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { ScoreBadge } from "./ScoreBadge";
import { SortMenu, type SortOption } from "./SortMenu";
import { useRouter } from "next/navigation";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  pageIndex?: number;
  hasPrev?: boolean;
  hasNext?: boolean;
  isPaging?: boolean;
  onPrev?: () => void;
  onNext?: () => void;
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
  return article.score ? "暂无摘要" : "未评分";
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
  pageIndex = 0,
  hasPrev = false,
  hasNext = false,
  isPaging = false,
  onPrev,
  onNext,
  notice,
}: ArticleListProps) {
  const router = useRouter();
  const isEmpty = articles.length === 0;

  function updateSort(nextSort: ArticleSortId) {
    const qs = new URLSearchParams({
      module: currentModule,
      sort: nextSort,
      lang: currentLang,
    });
    router.push(`?${qs.toString()}`);
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
          const focusHref = readHref(currentModule, currentSort, currentLang, article.id);
          return (
            <li key={article.id}>
              <article
                className="articleCard"
                role="link"
                tabIndex={0}
                aria-label={`${article.title}，进入专注阅读`}
                data-read-href={focusHref}
                onClick={() => router.push(focusHref)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") router.push(focusHref);
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
                    <ScoreBadge label="层级" value={tierLabel(score?.tier)} />
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
      {!isEmpty ? (
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
