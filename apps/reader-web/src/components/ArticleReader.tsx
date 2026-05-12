import type { Article } from "@/lib/articles/types";
import type { DimensionKey } from "@/lib/scoring/repository";
import { ScoreBadge } from "./ScoreBadge";

const DIMENSION_ROWS: { key: DimensionKey | "overall"; label: string }[] = [
  { key: "overall", label: "总分" },
  { key: "importance", label: "重要性" },
  { key: "usefulness", label: "实用性" },
  { key: "timeliness", label: "时效" },
  { key: "depth", label: "深度" },
  { key: "technical_value", label: "技术价值" },
  { key: "business_value", label: "商业价值" },
  { key: "trend_value", label: "趋势价值" },
];

export function ArticleReader({ article }: { article: Article | null }) {
  if (article == null) {
    return (
      <article className="articleReaderPane" aria-label="文章内容">
        <div className="readerEmpty">
          <p className="readerEmptyTitle">未选择文章</p>
          <p className="readerEmptyHint">从左侧列表选择一篇以阅读正文与评分。</p>
        </div>
      </article>
    );
  }

  const score = article.score;

  return (
    <article className="articleReaderPane" aria-label="文章内容">
      <header className="readerHeader">
        <div className="readerToolbar" role="toolbar" aria-label="阅读操作">
          <a
            className="readerToolbarBtn readerToolbarBtnPrimary"
            href={article.url}
            target="_blank"
            rel="noreferrer"
          >
            打开原文
          </a>
          <button type="button" className="readerToolbarBtn" disabled>
            专注阅读
          </button>
          <button type="button" className="readerToolbarBtn" disabled>
            收藏
          </button>
          <button type="button" className="readerToolbarBtn" disabled>
            稍后读
          </button>
        </div>
        <h2 className="readerTitle">{article.title}</h2>
      </header>

      <section className="scoreSection" aria-label="评分">
        <div className="scoreGrid">
          {DIMENSION_ROWS.map((row) => {
            const value =
              row.key === "overall"
                ? (score?.overall ?? null)
                : (score?.dimensions[row.key] ?? null);
            return <ScoreBadge key={row.key} label={row.label} value={value} />;
          })}
        </div>
        <p className="scoreReason">
          <span className="scoreReasonLabel">理由</span>
          {score?.reason?.trim()
            ? score.reason
            : "暂无评分说明（可能没有对应评分记录）。"}
        </p>
      </section>

      <div
        className="articleContent content"
        dangerouslySetInnerHTML={{ __html: article.contentHtml }}
      />
    </article>
  );
}
