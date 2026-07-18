"use client";

import { AnimatePresence } from "motion/react";
import Link from "next/link";
import { useRef, useState } from "react";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import type { ArticleStats } from "@/lib/api/articles";
import type { RecommendationPage } from "@/lib/api/recommendations";
import { AnimatedPanel } from "./AnimatedPanel";
import { ScoreRing } from "./ScoreRing";
import { SkeletonBlock } from "./Skeleton";
import { useDismissableLayer } from "./useDismissableLayer";

type WorkbenchRibbonProps = {
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
  defaultTop10Open?: boolean;
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

function adminHref(currentSort: ArticleSortId, currentLang: SummaryLangId): string {
  const qs = new URLSearchParams({
    module: "admin",
    sort: currentSort,
    lang: currentLang,
  });
  return `?${qs.toString()}`;
}

export function WorkbenchRibbon({
  recommendations,
  stats,
  currentModule,
  currentSort,
  currentLang,
  isLoading = false,
  notice,
  onRetry,
  defaultTop10Open = false,
}: WorkbenchRibbonProps) {
  const items = recommendations?.items.filter((item) => item.article != null) ?? [];
  const [top10Open, setTop10Open] = useState(defaultTop10Open);
  const top10Ref = useRef<HTMLDivElement | null>(null);

  useDismissableLayer({
    enabled: top10Open,
    layerRef: top10Ref,
    onDismiss: () => setTop10Open(false),
  });

  return (
    <section className="workbenchRibbon" aria-label="工作台状态">
      <div className="workbenchRibbonStats" aria-label="语料统计">
        {isLoading ? (
          <>
            <SkeletonBlock className="skeletonPill" width="72px" />
            <SkeletonBlock className="skeletonPill" width="72px" />
            <SkeletonBlock className="skeletonPill" width="72px" />
          </>
        ) : stats ? (
          <>
            <span>共 {stats.total}</span>
            <span>已评分 {stats.scored}</span>
            <span>待评分 {stats.unscored}</span>
            <Link className="workbenchRibbonLink" href="?module=review&sort=default&lang=zh" prefetch={false}>
              复习划线
            </Link>
            <a className="workbenchRibbonLink" href="/api/export/project?format=markdown">
              导出立项
            </a>
          </>
        ) : (
          <span className="workbenchRibbonMuted">统计待加载</span>
        )}
      </div>

      {notice ? (
        <div className="workbenchRibbonNotice" aria-live="polite">
          <span>
            <strong>{notice.title}</strong> {notice.body}
          </span>
          {onRetry ? (
            <button type="button" className="readerToolbarBtn" onClick={onRetry}>
              重试
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="workbenchRibbonActions">
        <div className="workbenchRibbonTop10" ref={top10Ref}>
          <button
            type="button"
            className="readerToolbarBtn workbenchRibbonTop10Button"
            aria-haspopup="dialog"
            aria-expanded={top10Open}
            aria-controls="workbench-top10"
            onClick={() => setTop10Open((value) => !value)}
          >
            Top10
          </button>
          <AnimatePresence initial={false}>
            {top10Open ? (
              <AnimatedPanel
                key="workbench-top10"
                id="workbench-top10"
                variant="popover"
                className="workbenchRibbonTop10Popover"
                role="dialog"
                aria-label="Top10 推荐"
              >
                {isLoading ? (
                  <div className="workbenchRibbonTop10Skeleton" aria-label="Top10 加载中" aria-busy="true">
                    {Array.from({ length: 5 }, (_, index) => (
                      <div className="workbenchRibbonTop10ItemSkeleton" key={index}>
                        <SkeletonBlock className="skeletonPill" width="28px" />
                        <SkeletonBlock className="skeletonLine" width="100%" />
                        <SkeletonBlock className="skeletonPill" width="46px" />
                      </div>
                    ))}
                  </div>
                ) : items.length > 0 ? (
                  <ol className="workbenchRibbonTop10List">
                    {items.map((item, index) => {
                      const article = item.article;
                      if (!article) return null;
                      const rank = item.rank || index + 1;
                      return (
                        <li key={`${rank}-${article.id}`}>
                          <Link
                            className="workbenchRibbonTop10Item"
                            href={readHref(currentModule, currentSort, currentLang, article.id)}
                            prefetch={false}
                          >
                            <span className="workbenchRibbonRank">#{rank}</span>
                            <span
                              className="workbenchRibbonTop10Title"
                              title={
                                item.factors
                                  ? `为什么：${item.factors.reason || item.reason} · 源=${item.factors.source} · 基分=${item.factors.baseScore ?? "—"}`
                                  : item.reason || undefined
                              }
                            >
                              {article.title}
                            </span>
                            <ScoreRing value={article.score?.overall ?? item.rankScore} tier={item.tier} size={46} />
                          </Link>
                        </li>
                      );
                    })}
                  </ol>
                ) : (
                  <p className="workbenchRibbonEmpty">Top10 尚未生成</p>
                )}
              </AnimatedPanel>
            ) : null}
          </AnimatePresence>
        </div>
        <Link className="readerToolbarBtn readerToolbarBtnPrimary" href={adminHref(currentSort, currentLang)} prefetch={false}>
          批量评分
        </Link>
      </div>
    </section>
  );
}
