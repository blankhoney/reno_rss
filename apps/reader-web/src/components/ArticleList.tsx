"use client";

import type { Article } from "@/lib/articles/types";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import type { ScoringSettings } from "@/lib/scoring/settings";
import { scoreArticlesWithConcurrency, type BulkScoreSummary } from "@/lib/scoring/bulkScore";
import { ScoreBadge } from "./ScoreBadge";
import { ScoringSettingsPanel } from "./ScoringSettingsPanel";
import { SortMenu, type SortOption } from "./SortMenu";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  selectedArticleId: number | null;
  initialScoringSettings: ScoringSettings;
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

export function scoreErrorMessage(error: string | undefined): string {
  if (error === "manual_rescore_disabled") return "手动重评已关闭";
  if (error === "entry_not_found") return "文章不存在或不在当前 Miniflux 实例";
  if (error === "score_service_invalid_response") return "评分服务返回异常";
  if (error === "score_failed") return "评分失败";
  if (error === undefined || error.trim().length === 0) return "未知错误";
  return error;
}

export function failedScoreMessages(summary: BulkScoreSummary): string[] {
  return summary.results
    .filter((result) => !result.ok)
    .map((result) => `#${result.entryId}：${scoreErrorMessage(result.error)}`);
}

export function ArticleList({
  articles,
  currentModule,
  currentSort,
  currentLang,
  selectedArticleId,
  initialScoringSettings,
}: ArticleListProps) {
  const router = useRouter();
  const isEmpty = articles.length === 0;
  const [manualBatchSize, setManualBatchSize] = useState(initialScoringSettings.manualBatchSize);
  const [manualRescoreEnabled, setManualRescoreEnabled] = useState(
    initialScoringSettings.manualRescoreEnabled,
  );
  const [bulkScoreSummary, setBulkScoreSummary] = useState<BulkScoreSummary | null>(null);
  const [isBulkScoring, setIsBulkScoring] = useState(false);
  const clickTimerRef = useRef<number | null>(null);
  const batchCount = Math.min(manualBatchSize, articles.length);
  const rescoreDisabledReason = !manualRescoreEnabled
    ? "手动重评已关闭"
    : batchCount === 0
      ? "暂无可重评文章"
      : null;
  const failedMessages = bulkScoreSummary ? failedScoreMessages(bulkScoreSummary) : [];

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

  async function rescoreCurrentPage() {
    if (isBulkScoring || rescoreDisabledReason != null) return;
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
  }

  return (
    <section className="articleListPane" aria-label="文章列表">
      <header className="articleListHeader">
        <h1 className="articleListTitle">阅读工作台</h1>
        <div className="articleListActions">
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={isBulkScoring || rescoreDisabledReason != null}
            title={rescoreDisabledReason ?? undefined}
            onClick={() => void rescoreCurrentPage()}
          >
            {isBulkScoring
              ? "重评中"
              : rescoreDisabledReason === "手动重评已关闭"
                ? "手动重评已关闭"
                : `重评前 ${batchCount} 篇`}
          </button>
          <ScoringSettingsPanel
            initialSettings={{
              ...initialScoringSettings,
              manualBatchSize,
              manualRescoreEnabled,
            }}
            onSettingsLoaded={(settings) => {
              setManualBatchSize(settings.manualBatchSize);
              setManualRescoreEnabled(settings.manualRescoreEnabled);
            }}
            onSettingsSaved={(settings) => {
              setManualBatchSize(settings.manualBatchSize);
              setManualRescoreEnabled(settings.manualRescoreEnabled);
            }}
          />
          <SortMenu currentSort={currentSort} options={SORT_OPTIONS} onChange={updateSort} />
        </div>
      </header>
      {bulkScoreSummary ? (
        <div className="bulkScoreStatus" role="status">
          <p>
            {isBulkScoring ? "重评进度" : "重评完成"} {bulkScoreSummary.completed}/
            {bulkScoreSummary.total}，成功 {bulkScoreSummary.succeeded}，失败{" "}
            {bulkScoreSummary.failed}
          </p>
          {failedMessages.length > 0 ? (
            <ul className="bulkScoreFailures" aria-label="评分失败文章">
              {failedMessages.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          ) : null}
          {!isBulkScoring && bulkScoreSummary.completed > 0 ? (
            <button
              type="button"
              className="bulkScoreRefresh"
              onClick={() => router.refresh()}
            >
              刷新列表查看摘要/评分
            </button>
          ) : null}
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
