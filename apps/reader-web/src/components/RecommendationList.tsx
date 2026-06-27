"use client";

import { useRouter } from "next/navigation";
import type { ArticleSortId, SummaryLangId } from "@/lib/articles/service";
import type { RecommendationItem, RecommendationPage } from "@/lib/api/recommendations";
import { ScoreBadge } from "./ScoreBadge";

type RecommendationListProps = {
  page: RecommendationPage;
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

function latestHref(currentLang: SummaryLangId): string {
  const qs = new URLSearchParams({ module: "all", sort: "latest", lang: currentLang });
  return `?${qs.toString()}`;
}

function formatGeneratedAt(value: string | null): string {
  if (value == null || value.trim().length === 0) return "生成时间待确认";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(
    date.getUTCHours(),
  )}:${pad(date.getUTCMinutes())} UTC`;
}

function sourceLabel(source: string): string {
  if (source === "subscription") return "订阅";
  if (source === "exploration") return "探索";
  return source;
}

function riskText(item: RecommendationItem): string {
  const flags = item.riskFlags.length > 0 ? item.riskFlags.join(", ") : "待评估";
  return item.riskUncertainty == null ? flags : `${flags} / 不确定性 ${item.riskUncertainty}`;
}

export function RecommendationList({
  page,
  currentModule,
  currentSort,
  currentLang,
}: RecommendationListProps) {
  const router = useRouter();

  return (
    <section className="articleListPane" aria-label="今日 Top10">
      <header className="articleListHeader">
        <div>
          <h1 className="articleListTitle">今日 Top10</h1>
          <p className="recommendationEdition">
            {page.edition
              ? `${formatGeneratedAt(page.edition.generatedAt)} / ${page.edition.algorithmVersion}`
              : "等待同步和评分生成推荐版次"}
          </p>
          <p className="recommendationEdition">Top10 · 固定榜单</p>
        </div>
        <div className="articleListActions">
          <a className="readerToolbarBtn" href={latestHref(currentLang)}>
            查看最新文章
          </a>
        </div>
      </header>

      {page.items.length === 0 ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">Top10 尚未生成</p>
          <p className="articleListEmptyHint">需要先完成同步和评分；你仍可以查看最新文章。</p>
        </div>
      ) : null}

      <ul className="articleList">
        {page.items.map((item) => {
          const article = item.article;
          const articleId = article?.id ?? item.rank;
          const focusHref = article ? readHref(currentModule, currentSort, currentLang, article.id) : null;
          return (
            <li key={`${item.rank}-${articleId}`}>
              <article
                className="articleCard recommendationCard"
                role={focusHref ? "link" : undefined}
                tabIndex={focusHref ? 0 : undefined}
                aria-label={
                  article
                    ? `${article.title}，Top10 第 ${item.rank} 名，进入专注阅读`
                    : `Top10 第 ${item.rank} 名文章暂不可用`
                }
                data-read-href={focusHref ?? undefined}
                onClick={() => {
                  if (focusHref) router.push(focusHref);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && focusHref) router.push(focusHref);
                }}
              >
                <div className="recommendationTopline">
                  <span className="recommendationRank">#{item.rank}</span>
                  <span className="recommendationPill">{item.tier}</span>
                  <span className="recommendationPill">{sourceLabel(item.source)}</span>
                </div>
                <div className="articleCardMeta">
                  <span className="articleFeed">{article?.feedTitle ?? "来源待确认"}</span>
                  {article?.categoryTitle ? (
                    <span className="articleCategory">{article.categoryTitle}</span>
                  ) : null}
                </div>
                <div className="articleCardTitle">{article?.title ?? "文章暂不可用"}</div>
                <p className="recommendationReason">{item.reason || "推荐理由待生成。"}</p>
                <div className="recommendationMetrics">
                  <ScoreBadge label="Rank" value={item.rankScore} />
                  <span className="recommendationRisk">风险：{riskText(item)}</span>
                  <span className="recommendationRisk">
                    文章评分：{article?.score?.overall ?? "待生成"}
                  </span>
                </div>
                {focusHref ? (
                  <div className="articleCardFooter">
                    <a
                      className="articleReadLink"
                      href={focusHref}
                      onClick={(event) => event.stopPropagation()}
                      onDoubleClick={(event) => event.stopPropagation()}
                    >
                      阅读
                    </a>
                  </div>
                ) : null}
              </article>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
