"use client";

import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import type { ArticleStats } from "@/lib/api/articles";
import type { RecommendationPage } from "@/lib/api/recommendations";
import { ScoreBadge } from "./ScoreBadge";

type WorkbenchRailProps = {
  recommendations: RecommendationPage | null;
  stats: ArticleStats | null;
  currentModule: string;
  currentSort: ArticleSortId;
  currentLang: SummaryLangId;
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
}: WorkbenchRailProps) {
  const items = recommendations?.items.filter((item) => item.article != null) ?? [];

  return (
    <aside className="workbenchRail" aria-label="工作台信息">
      <section className="workbenchRailSection">
        <h2 className="workbenchRailTitle">Top10</h2>
        {items.length > 0 ? (
          <ol className="workbenchRailList">
            {items.map((item, index) => {
              const article = item.article;
              if (!article) return null;
              const rank = item.rank || index + 1;
              return (
                <li key={`${rank}-${article.id}`}>
                  <a
                    className="workbenchRailItem"
                    href={readHref(currentModule, currentSort, currentLang, article.id)}
                  >
                    <span className="workbenchRailRank">#{rank}</span>
                    <span className="workbenchRailItemTitle">{article.title}</span>
                    <ScoreBadge label="总分" value={article.score?.overall ?? item.rankScore} />
                  </a>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="workbenchRailEmpty">Top10 尚未生成</p>
        )}
      </section>

      <section className="workbenchRailSection">
        <h2 className="workbenchRailTitle">语料统计</h2>
        {stats ? (
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
