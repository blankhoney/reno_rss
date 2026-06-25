"use client";

import { useEffect, useState } from "react";
import type { Article } from "@/lib/articles/types";
import { createThinkTagFilter } from "@/lib/agent/stream";
import { streamArticleAsk } from "@/lib/api/client";
import type { SummaryLangId } from "@/lib/articles/service";
import type { DimensionKey } from "@/lib/scoring/repository";
import { AgentMarkdown } from "./AgentMarkdown";
import { ScoreBadge } from "./ScoreBadge";
import { articleAskErrorMessage } from "./articleAsk";
import { articleAgentNotice, articleContentNotice } from "./articleContentNotice";
import { useArticleActions } from "./useArticleActions";

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

function selectedTextFromPage(): string | undefined {
  const text = window.getSelection()?.toString().trim();
  return text && text.length > 0 ? text : undefined;
}

function summaryForLang(article: Article, lang: SummaryLangId): string {
  const summary = lang === "original" ? article.summaryOriginal || article.summaryZh : article.summaryZh;
  return summary.trim() || "暂无摘要，点击实时评分生成";
}

function switchSummaryLang(nextLang: SummaryLangId) {
  const qs = new URLSearchParams(window.location.search);
  qs.set("lang", nextLang);
  window.location.search = qs.toString();
}

export function ArticleReader({
  article,
  currentLang,
}: {
  article: Article | null;
  currentLang: SummaryLangId;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const articleActions = useArticleActions(article, currentLang);

  useEffect(() => {
    setQuestion("");
    setAnswer("");
    setAgentError(null);
  }, [article?.id]);

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
  const canAsk = question.trim().length > 0 && !isAsking;
  const contentNotice = articleContentNotice(article);
  const agentNotice = articleAgentNotice(article);

  async function askAgent() {
    if (article == null || question.trim().length === 0) return;

    setIsAsking(true);
    setAnswer("");
    setAgentError(null);

    try {
      const thinkFilter = createThinkTagFilter();
      for await (const chunk of streamArticleAsk(article.id, {
        question,
        selected_text: selectedTextFromPage(),
      })) {
        const text = thinkFilter.push(chunk);
        if (text.length > 0) setAnswer((current) => current + text);
      }
      const finalText = thinkFilter.flush();
      if (finalText.length > 0) setAnswer((current) => current + finalText);
    } catch (error) {
      setAgentError(articleAskErrorMessage(error));
    } finally {
      setIsAsking(false);
    }
  }

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
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={articleActions.isFetchingContent}
            onClick={() => void articleActions.refreshFullContent()}
          >
            {articleActions.isFetchingContent ? "刷新中" : "刷新全文"}
          </button>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={articleActions.isScoring}
            onClick={() => void articleActions.scoreNow()}
          >
            {articleActions.isScoring ? "评分中" : "实时评分"}
          </button>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={articleActions.isTogglingCandidate}
            onClick={() => void articleActions.toggleCandidate()}
          >
            {article.starred ? "移出候选" : "加入候选"}
          </button>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={articleActions.isProjecting}
            onClick={() => void articleActions.enqueueProject()}
          >
            {articleActions.isProjecting ? "立项中" : "立项"}
          </button>
        </div>
        {articleActions.actionMessage ? (
          <p className="readerActionMessage">
            {articleActions.actionMessage}
            {articleActions.actionLink ? (
              <>
                {" "}
                <a href={articleActions.actionLink.href}>{articleActions.actionLink.label}</a>
              </>
            ) : null}
          </p>
        ) : null}
        {articleActions.actionError ? (
          <p className="readerActionError">{articleActions.actionError}</p>
        ) : null}
        <h2 className="readerTitle">{article.title}</h2>
        <section className="readerSummary" aria-label="文章摘要">
          <div className="readerSummaryHeader">
            <span>摘要</span>
            <div className="readerLangToggle" aria-label="摘要语言">
              <button
                type="button"
                className={currentLang === "zh" ? "readerLangBtn readerLangBtnActive" : "readerLangBtn"}
                onClick={() => switchSummaryLang("zh")}
              >
                中文摘要
              </button>
              <button
                type="button"
                className={
                  currentLang === "original" ? "readerLangBtn readerLangBtnActive" : "readerLangBtn"
                }
                onClick={() => switchSummaryLang("original")}
              >
                原文摘要
              </button>
            </div>
          </div>
          <p>{summaryForLang(article, currentLang)}</p>
        </section>
      </header>

      <section className="scoreSection" aria-label="评分">
        {score ? (
          <>
            <div className="scoreGrid">
              {DIMENSION_ROWS.map((row) => {
                const value =
                  row.key === "overall" ? score.overall : score.dimensions[row.key];
                return <ScoreBadge key={row.key} label={row.label} value={value} />;
              })}
            </div>
            <p className="scoreReason">
              <span className="scoreReasonLabel">总评</span>
              {score.reason.trim() || "暂无评分理由。"}
            </p>
            {Object.keys(score.dimensionReasons).length > 0 ? (
              <details className="dimensionReasons">
                <summary>维度理由</summary>
                <dl>
                  {DIMENSION_ROWS.filter((row): row is { key: DimensionKey; label: string } => row.key !== "overall")
                    .filter((row) => score.dimensionReasons[row.key])
                    .map((row) => (
                      <div key={row.key} className="dimensionReasonRow">
                        <dt>{row.label}</dt>
                        <dd>{score.dimensionReasons[row.key]}</dd>
                      </div>
                    ))}
                </dl>
              </details>
            ) : null}
          </>
        ) : (
          <p className="scoreMissing">未评分。点击“实时评分”生成摘要、分数和理由。</p>
        )}
      </section>

      {contentNotice ? <p className="contentPartialNotice">{contentNotice}</p> : null}

      <div
        className="articleContent content"
        dangerouslySetInnerHTML={{ __html: article.contentHtml }}
      />

      <section className="agentPanel" aria-label="当前文章问答">
        <div className="agentHeader">
          <h3 className="agentTitle">文章问答</h3>
          <button
            type="button"
            className="readerToolbarBtn readerToolbarBtnPrimary"
            disabled={!canAsk}
            onClick={() => void askAgent()}
          >
            {isAsking ? "生成中" : "询问"}
          </button>
        </div>
        <textarea
          className="agentQuestion"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="问当前文章..."
          rows={3}
        />
        {agentNotice ? <p className="agentNotice">{agentNotice}</p> : null}
        {agentError != null ? <p className="agentError">{agentError}</p> : null}
        {answer.trim().length > 0 ? <AgentMarkdown text={answer} /> : null}
      </section>

    </article>
  );
}
