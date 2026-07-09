import type { CSSProperties } from "react";
import Link from "next/link";

function styleWithWidth(width?: string): CSSProperties | undefined {
  return width ? { width } : undefined;
}

export function SkeletonBlock({
  className = "",
  width,
}: {
  className?: string;
  width?: string;
}) {
  return (
    <span
      className={className ? `skeletonBlock ${className}` : "skeletonBlock"}
      style={styleWithWidth(width)}
      aria-hidden="true"
    />
  );
}

export function ArticleListSkeleton({ count = 12 }: { count?: number }) {
  return (
    <ul className="articleList articleListSkeleton" aria-label="文章加载中" aria-busy="true">
      {Array.from({ length: count }, (_, index) => (
        <li key={index}>
          <article
            className={
              index === 0
                ? "articleCard articleCardHeadline articleCardSkeleton"
                : "articleCard articleCardSkeleton"
            }
          >
            <div className="articleCardMeta">
              <SkeletonBlock className="skeletonPill" width="72px" />
              <SkeletonBlock className="skeletonPill" width="44px" />
            </div>
            <SkeletonBlock
              className={
                index === 0
                  ? "skeletonLine skeletonTitleLine skeletonHeadlineTitle"
                  : "skeletonLine skeletonTitleLine"
              }
              width="86%"
            />
            <SkeletonBlock className="skeletonLine" width="100%" />
            <SkeletonBlock className="skeletonLine" width="68%" />
            <div className="articleCardFooter">
              <div className="articleCardScoreBlock">
                <SkeletonBlock
                  className={
                    index === 0
                      ? "skeletonScoreRing skeletonScoreRingLarge"
                      : "skeletonScoreRing"
                  }
                />
              </div>
              <SkeletonBlock className="skeletonPill" width="42px" />
            </div>
          </article>
        </li>
      ))}
    </ul>
  );
}

export function FocusedArticleSkeleton({ returnHref }: { returnHref: string }) {
  return (
    <main className="focusReader" aria-busy="true">
      <header className="focusTopbar">
        <Link className="readerToolbarBtn" href={returnHref} prefetch={false}>
          返回工作台
        </Link>
        <SkeletonBlock className="skeletonPill" width="72px" />
        <SkeletonBlock className="skeletonPill" width="88px" />
      </header>
      <section className="focusStatusBar" aria-label="阅读状态加载中">
        <SkeletonBlock className="skeletonPill" width="78px" />
        <SkeletonBlock className="skeletonPill" width="82px" />
        <SkeletonBlock className="skeletonPill" width="92px" />
      </section>
      <article className="focusArticle focusArticleSkeleton" aria-label="文章加载中">
        <header className="focusArticleHeader">
          <SkeletonBlock className="skeletonLine" width="42%" />
          <SkeletonBlock className="skeletonLine skeletonHeroLine" width="92%" />
          <SkeletonBlock className="skeletonLine skeletonHeroLine" width="64%" />
        </header>
        <div className="focusSection">
          <SkeletonBlock className="skeletonLine" width="36%" />
          <SkeletonBlock className="skeletonLine" width="100%" />
          <SkeletonBlock className="skeletonLine" width="72%" />
        </div>
        <div className="focusSection focusScoreSkeleton">
          <SkeletonBlock className="skeletonLine" width="24%" />
          <div className="scoreOverview">
            <SkeletonBlock className="skeletonScoreRing" />
            <div>
              <SkeletonBlock className="skeletonLine" width="34%" />
              <SkeletonBlock className="skeletonLine" width="82%" />
            </div>
          </div>
          <div className="dimensionBars">
            {Array.from({ length: 8 }, (_, index) => (
              <div className="dimensionBarRow skeletonDimensionBarRow" key={index}>
                <SkeletonBlock className="skeletonLine" width="76px" />
                <SkeletonBlock className="skeletonLine" width="100%" />
                <SkeletonBlock className="skeletonLine" width="24px" />
              </div>
            ))}
          </div>
        </div>
        <div className="focusContentSkeleton">
          {["100%", "96%", "82%", "98%", "74%", "92%"].map((width) => (
            <SkeletonBlock className="skeletonLine" width={width} key={width} />
          ))}
        </div>
      </article>
    </main>
  );
}
