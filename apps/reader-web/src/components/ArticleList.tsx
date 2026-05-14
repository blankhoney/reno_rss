"use client";

import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { ScoreBadge } from "./ScoreBadge";
import { ScoringSettingsPanel } from "./ScoringSettingsPanel";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  selectedArticleId: number | null;
};

const SORT_OPTIONS: { id: ArticleSortId; label: string }[] = [
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

function articleSummary(article: Article, currentLang: SummaryLangId): string {
  const summary =
    currentLang === "original" ? article.summaryOriginal || article.summaryZh : article.summaryZh;
  return summary.trim() || "暂无摘要，点击实时评分生成";
}

export function ArticleList({
  articles,
  currentModule,
  currentSort,
  currentLang,
  selectedArticleId,
}: ArticleListProps) {
  const isEmpty = articles.length === 0;

  function updateSort(nextSort: ArticleSortId) {
    const qs = new URLSearchParams(window.location.search);
    qs.set("module", currentModule);
    qs.set("sort", nextSort);
    qs.set("lang", currentLang);
    window.location.search = qs.toString();
  }

  return (
    <section className="articleListPane" aria-label="文章列表">
      <header className="articleListHeader">
        <h1 className="articleListTitle">阅读工作台</h1>
        <div className="articleListActions">
          <ScoringSettingsPanel />
          <label className="articleSortLabel">
            <span className="visuallyHidden">排序</span>
            <select
              className="articleSortSelect"
              value={currentSort}
              aria-label="排序方式"
              onChange={(event) => updateSort(event.target.value as ArticleSortId)}
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>
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
          return (
            <li key={article.id}>
              <a
                className={`articleCard${isActive ? " articleCardActive" : ""}`}
                href={listHref(currentModule, currentSort, currentLang, article.id)}
                aria-current={isActive ? "true" : undefined}
              >
                <div className="articleCardMeta">
                  <span className="articleFeed">{article.feedTitle}</span>
                  {article.categoryTitle ? (
                    <span className="articleCategory">{article.categoryTitle}</span>
                  ) : null}
                </div>
                <div className="articleCardTitle">{article.title}</div>
                <p className="articleCardSummary">{articleSummary(article, currentLang)}</p>
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
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
