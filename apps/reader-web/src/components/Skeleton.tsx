import type { CSSProperties } from "react";

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
          <article className="articleCard articleCardSkeleton">
            <div className="articleCardMeta">
              <SkeletonBlock className="skeletonPill" width="72px" />
              <SkeletonBlock className="skeletonPill" width="44px" />
            </div>
            <SkeletonBlock className="skeletonLine skeletonTitleLine" width="86%" />
            <SkeletonBlock className="skeletonLine" width="100%" />
            <SkeletonBlock className="skeletonLine" width="68%" />
            <div className="articleCardFooter">
              <div className="articleCardScores">
                <SkeletonBlock className="skeletonPill" width="66px" />
              </div>
              <SkeletonBlock className="skeletonPill" width="42px" />
            </div>
          </article>
        </li>
      ))}
    </ul>
  );
}

export function WorkbenchRailSkeleton() {
  return (
    <div className="workbenchRailSkeleton" aria-label="右栏加载中" aria-busy="true">
      <div className="workbenchRailSkeletonList">
        {Array.from({ length: 5 }, (_, index) => (
          <div className="workbenchRailItem workbenchRailItemSkeleton" key={index}>
            <SkeletonBlock className="skeletonPill" width="28px" />
            <SkeletonBlock className="skeletonLine" width="100%" />
            <SkeletonBlock className="skeletonPill" width="58px" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function WorkbenchStatsSkeleton() {
  return (
    <div className="workbenchStats workbenchStatsSkeleton" aria-label="统计加载中" aria-busy="true">
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index}>
          <SkeletonBlock className="skeletonLine" width="54px" />
          <SkeletonBlock className="skeletonPill" width="34px" />
        </div>
      ))}
    </div>
  );
}

export function FocusedArticleSkeleton({ returnHref }: { returnHref: string }) {
  return (
    <main className="focusReader" aria-busy="true">
      <header className="focusTopbar">
        <a className="readerToolbarBtn" href={returnHref}>
          返回工作台
        </a>
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
        <div className="focusContentSkeleton">
          {["100%", "96%", "82%", "98%", "74%", "92%"].map((width) => (
            <SkeletonBlock className="skeletonLine" width={width} key={width} />
          ))}
        </div>
      </article>
    </main>
  );
}
