"use client";

import { useEffect, useState } from "react";
import type { Article } from "@/lib/articles/types";
import { createThinkTagFilter, extractOpenAICompatibleEventText } from "@/lib/agent/stream";
import type { SummaryLangId } from "@/lib/articles/service";
import type { DimensionKey } from "@/lib/scoring/repository";
import { AgentMarkdown } from "./AgentMarkdown";
import { ScoreBadge } from "./ScoreBadge";
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

function htmlToText(html: string): string {
  const element = document.createElement("div");
  element.innerHTML = html;
  return (element.textContent ?? element.innerText ?? "").replace(/\s+/g, " ").trim();
}

function articleContextText(article: Article): string {
  const body = htmlToText(article.contentHtml);
  const parts = [
    `标题：${article.title}`,
    `链接：${article.url}`,
    `正文状态：${article.contentStatus === "partial" ? "当前可能只有 RSS 片段" : "完整或较完整正文"}`,
    article.summaryZh ? `中文摘要：${article.summaryZh}` : "",
    article.summaryOriginal ? `原文摘要：${article.summaryOriginal}` : "",
    article.score?.reason ? `评分理由：${article.score.reason}` : "",
    body,
  ].filter((part) => part.trim().length > 0);
  return parts.join("\n\n").slice(0, 20000);
}

function selectedTextFromPage(): string | undefined {
  const text = window.getSelection()?.toString().trim();
  return text && text.length > 0 ? text : undefined;
}

function appendAgentStreamChunk(
  chunk: string,
  pending: string,
  thinkFilter: ReturnType<typeof createThinkTagFilter>,
  append: (text: string) => void,
): string {
  const combined = pending + chunk;
  const events = combined.split(/\r?\n\r?\n/);
  const nextPending = events.pop() ?? "";

  for (const event of events) {
    const dataLines = event
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice("data:".length).trimStart());

    if (dataLines.length === 0) {
      append(thinkFilter.push(event));
      continue;
    }

    for (const data of dataLines) {
      append(thinkFilter.push(extractOpenAICompatibleEventText(data)));
    }
  }

  return nextPending;
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
      const response = await fetch("/api/agent/article-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          selectedText: selectedTextFromPage(),
          article: {
            title: article.title,
            url: article.url,
            contentText: articleContextText(article),
            contentStatus: article.contentStatus,
            scoreReason: article.score?.reason ?? "",
            tags: article.score?.tags ?? [],
          },
        }),
      });

      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { error?: unknown } | null;
        throw new Error(typeof body?.error === "string" ? body.error : "Agent request failed.");
      }
      const stream = response.body;
      if (stream == null) throw new Error("Agent response missing stream.");

      const reader = stream.getReader();
      const decoder = new TextDecoder();
      const thinkFilter = createThinkTagFilter();
      let pending = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending = appendAgentStreamChunk(
          decoder.decode(value, { stream: true }),
          pending,
          thinkFilter,
          (text) => {
            if (text.length > 0) setAnswer((current) => current + text);
          },
        );
      }

      const tail = decoder.decode();
      pending = appendAgentStreamChunk(tail, pending, thinkFilter, (text) => {
        if (text.length > 0) setAnswer((current) => current + text);
      });
      if (pending.trim().length > 0) {
        appendAgentStreamChunk("\n\n", pending, thinkFilter, (text) => {
          if (text.length > 0) setAnswer((current) => current + text);
        });
      }
      const finalText = thinkFilter.flush();
      if (finalText.length > 0) setAnswer((current) => current + finalText);
    } catch (error) {
      setAgentError(error instanceof Error ? error.message : "Agent request failed.");
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
