"use client";

import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import { DEFAULT_SCORING_SETTINGS, type ScoringSettings } from "@/lib/scoring/settings";
import { scoreArticlesWithConcurrency, type BulkScoreSummary } from "@/lib/scoring/bulkScore";
import { ScoreBadge } from "./ScoreBadge";
import { ScoringSettingsPanel } from "./ScoringSettingsPanel";
import { useEffect, useState } from "react";

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
  return summary.trim() || "未生成摘要";
}

async function scoreArticle(entryId: number, force: boolean) {
  const response = await fetch(`/api/articles/${entryId}/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  const body = (await response.json().catch(() => null)) as { ok?: unknown; error?: unknown } | null;
  if (!response.ok || body?.ok !== true) {
    return {
      ok: false,
      entryId,
      error: typeof body?.error === "string" ? body.error : "score_failed",
    };
  }
  return { ok: true, entryId };
}

export function ArticleList({
  articles,
  currentModule,
  currentSort,
  currentLang,
  selectedArticleId,
}: ArticleListProps) {
  const isEmpty = articles.length === 0;
  const [manualBatchSize, setManualBatchSize] = useState(DEFAULT_SCORING_SETTINGS.manualBatchSize);
  const [bulkScoreSummary, setBulkScoreSummary] = useState<BulkScoreSummary | null>(null);
  const [isBulkScoring, setIsBulkScoring] = useState(false);
  const batchCount = Math.min(manualBatchSize, articles.length);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/scoring/settings", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("settings_fetch_failed");
        return response.json() as Promise<{ settings: ScoringSettings }>;
      })
      .then((body) => {
        if (!cancelled) setManualBatchSize(body.settings.manualBatchSize);
      })
      .catch(() => {
        if (!cancelled) setManualBatchSize(DEFAULT_SCORING_SETTINGS.manualBatchSize);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function updateSort(nextSort: ArticleSortId) {
    const qs = new URLSearchParams(window.location.search);
    qs.set("module", currentModule);
    qs.set("sort", nextSort);
    qs.set("lang", currentLang);
    if (selectedArticleId != null) qs.set("article", String(selectedArticleId));
    window.location.search = qs.toString();
  }

  async function rescoreCurrentPage() {
    if (isBulkScoring || batchCount === 0) return;
    setIsBulkScoring(true);
    setBulkScoreSummary({
      total: batchCount,
      completed: 0,
      succeeded: 0,
      failed: 0,
      results: [],
    });
    const summary = await scoreArticlesWithConcurrency(
      articles.map((article) => article.id),
      {
        limit: manualBatchSize,
        concurrency: 3,
        scoreEntry: scoreArticle,
        onProgress: setBulkScoreSummary,
      },
    );
    setBulkScoreSummary(summary);
    setIsBulkScoring(false);
    window.setTimeout(() => window.location.reload(), 700);
  }

  return (
    <section className="articleListPane" aria-label="文章列表">
      <header className="articleListHeader">
        <h1 className="articleListTitle">阅读工作台</h1>
        <div className="articleListActions">
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={isBulkScoring || batchCount === 0}
            onClick={() => void rescoreCurrentPage()}
          >
            {isBulkScoring ? "重评中" : `重评前 ${batchCount} 篇`}
          </button>
          <ScoringSettingsPanel
            onSettingsLoaded={(settings) => setManualBatchSize(settings.manualBatchSize)}
            onSettingsSaved={(settings) => setManualBatchSize(settings.manualBatchSize)}
          />
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
      {bulkScoreSummary ? (
        <p className="bulkScoreStatus">
          重评进度 {bulkScoreSummary.completed}/{bulkScoreSummary.total}，成功{" "}
          {bulkScoreSummary.succeeded}，失败 {bulkScoreSummary.failed}
        </p>
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
