"use client";

import { useState } from "react";
import Link from "next/link";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import type { ArticleStats } from "@/lib/api/articles";
import type { RecommendationPage } from "@/lib/api/recommendations";
import { ScoreBadge } from "./ScoreBadge";
import { WorkbenchRailSkeleton, WorkbenchStatsSkeleton } from "./Skeleton";

type WorkbenchRailProps = {
  recommendations: RecommendationPage | null;
  stats: ArticleStats | null;
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
  isLoading?: boolean;
  notice?: {
    title: string;
    body: string;
  };
  onRetry?: () => void;
};

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

export function WorkbenchRail({
  recommendations,
  stats,
  currentModule,
  currentSort,
  currentLang,
  isLoading = false,
  notice,
  onRetry,
}: WorkbenchRailProps) {
  const items = recommendations?.items.filter((item) => item.article != null) ?? [];
  const [top10Open, setTop10Open] = useState(false);

  return (
    <aside className="workbenchRail" aria-label="工作台信息">
      {notice ? (
        <section className="workbenchRailSection" aria-live="polite">
          <h2 className="workbenchRailTitle">{notice.title}</h2>
          <p className="workbenchRailEmpty">{notice.body}</p>
          {onRetry ? (
            <button type="button" className="readerToolbarBtn" onClick={onRetry}>
              重试
            </button>
          ) : null}
        </section>
      ) : null}
      <section className="workbenchRailSection">
        <button
          type="button"
          className="workbenchRailToggle"
          aria-expanded={top10Open}
          aria-controls="workbench-top10"
          onClick={() => setTop10Open((value) => !value)}
        >
          <span>Top10</span>
          <span aria-hidden="true">{top10Open ? "−" : "+"}</span>
        </button>
        <h2 className="workbenchRailTitle workbenchRailDesktopTitle">Top10</h2>
        <div
          id="workbench-top10"
          className={top10Open ? "workbenchRailCollapsible workbenchRailCollapsibleOpen" : "workbenchRailCollapsible"}
        >
          {isLoading ? (
            <WorkbenchRailSkeleton />
          ) : items.length > 0 ? (
            <ol className="workbenchRailList">
              {items.map((item, index) => {
                const article = item.article;
                if (!article) return null;
                const rank = item.rank || index + 1;
                return (
                  <li key={`${rank}-${article.id}`}>
                    <Link
                      className="workbenchRailItem"
                      href={readHref(currentModule, currentSort, currentLang, article.id)}
                      prefetch={false}
                    >
                      <span className="workbenchRailRank">#{rank}</span>
                      <span className="workbenchRailItemTitle">{article.title}</span>
                      <ScoreBadge label="总分" value={article.score?.overall ?? item.rankScore} />
                    </Link>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="workbenchRailEmpty">Top10 尚未生成</p>
          )}
        </div>
      </section>

      <section className="workbenchRailSection">
        <h2 className="workbenchRailTitle">语料统计</h2>
        {isLoading ? (
          <WorkbenchStatsSkeleton />
        ) : stats ? (
          <dl className="workbenchStats">
            <div>
              <dt>共</dt>
              <dd>{stats.total}</dd>
            </div>
            <div>
              <dt>已评分</dt>
              <dd>{stats.scored}</dd>
            </div>
            <div>
              <dt>待评分</dt>
              <dd>{stats.unscored}</dd>
            </div>
          </dl>
        ) : (
          <p className="workbenchRailEmpty">统计待加载</p>
        )}
      </section>
    </aside>
  );
}
