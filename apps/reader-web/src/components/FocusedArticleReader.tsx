"use client";

import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { Article } from "@/lib/articles/types";
import type { SummaryLangId } from "@/lib/articles/service";
import type { DimensionKey } from "@/lib/scoring/repository";
import { createThinkTagFilter, extractOpenAICompatibleEventText } from "@/lib/agent/stream";
import { AgentMarkdown } from "./AgentMarkdown";
import { ScoreBadge } from "./ScoreBadge";
import { articleAgentNotice, articleContentNotice } from "./articleContentNotice";
import { useArticleActions } from "./useArticleActions";
import { useDismissableLayer } from "./useDismissableLayer";

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

const QUICK_ACTIONS = [
  { label: "总结", question: "请总结这篇文章的核心内容。" },
  { label: "要点", question: "请提炼这篇文章最重要的 5 个要点。" },
  { label: "解释选中", question: "请解释我选中的这段内容；如果没有选中文字，请解释文章里的关键概念。" },
  { label: "行动建议", question: "基于这篇文章，给出可执行的行动建议。" },
];

function htmlToText(html: string): string {
  const element = document.createElement("div");
  element.innerHTML = html;
  return (element.textContent ?? element.innerText ?? "").replace(/\s+/g, " ").trim();
}

function selectedTextFromPage(): string | undefined {
  const text = window.getSelection()?.toString().trim();
  return text && text.length > 0 ? text : undefined;
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

export function FocusedArticleReader({
  article,
  currentLang,
  returnHref,
}: {
  article: Article;
  currentLang: SummaryLangId;
  returnHref: string;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef<HTMLElement | null>(null);
  const articleActions = useArticleActions(article, currentLang);

  useDismissableLayer({
    enabled: drawerOpen,
    layerRef: drawerRef,
    onDismiss: () => setDrawerOpen(false),
  });

  useEffect(() => {
    if (!drawerOpen || isAsking) return;
    const closeOnScroll = () => setDrawerOpen(false);
    const closeOnPageWheel = (event: WheelEvent) => {
      if ((event.target as Element | null)?.closest(".agentDrawer")) return;
      setDrawerOpen(false);
    };
    const closeOnPageTouchMove = (event: TouchEvent) => {
      if ((event.target as Element | null)?.closest(".agentDrawer")) return;
      setDrawerOpen(false);
    };
    window.addEventListener("scroll", closeOnScroll, { passive: true });
    window.addEventListener("wheel", closeOnPageWheel, { passive: true, capture: true });
    window.addEventListener("touchmove", closeOnPageTouchMove, { passive: true, capture: true });
    return () => {
      window.removeEventListener("scroll", closeOnScroll);
      window.removeEventListener("wheel", closeOnPageWheel, { capture: true });
      window.removeEventListener("touchmove", closeOnPageTouchMove, { capture: true });
    };
  }, [drawerOpen, isAsking]);

  async function askAgent(nextQuestion = question) {
    const trimmedQuestion = nextQuestion.trim();
    if (trimmedQuestion.length === 0) return;

    setDrawerOpen(true);
    setQuestion(trimmedQuestion);
    setIsAsking(true);
    setAnswer("");
    setAgentError(null);

    try {
      const response = await fetch("/api/agent/article-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: trimmedQuestion,
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

  const score = article.score;
  const contentNotice = articleContentNotice(article);
  const agentNotice = articleAgentNotice(article);

  return (
    <main className="focusReader">
      <header className="focusTopbar">
        <a className="readerToolbarBtn" href={returnHref}>
          返回工作台
        </a>
        <a className="readerToolbarBtn readerToolbarBtnPrimary" href={article.url} target="_blank" rel="noreferrer">
          打开原文
        </a>
        <div className="focusActionBar" role="toolbar" aria-label="文章操作">
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
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={articleActions.isMarkingRead}
            onClick={() => void articleActions.markRead()}
          >
            {articleActions.isMarkingRead ? "标记中" : "标记已读"}
          </button>
        </div>
      </header>

      <section className="focusStatusBar" aria-label="阅读状态">
        <span>{article.contentStatus === "partial" ? "正文：片段" : "正文：完整"}</span>
        <span>{score ? "评分：已评分" : "评分：未评分"}</span>
      </section>

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

      <article className="focusArticle">
        <header className="focusArticleHeader">
          <p className="focusArticleMeta">
            {article.feedTitle}
            {article.categoryTitle ? ` / ${article.categoryTitle}` : ""}
          </p>
          <h1>{article.title}</h1>
        </header>

        <details className="focusSection" open>
          <summary>摘要</summary>
          <div className="readerLangToggle focusLangToggle" aria-label="摘要语言">
            <button
              type="button"
              className={currentLang === "zh" ? "readerLangBtn readerLangBtnActive" : "readerLangBtn"}
              onClick={() => switchSummaryLang("zh")}
            >
              中文摘要
            </button>
            <button
              type="button"
              className={currentLang === "original" ? "readerLangBtn readerLangBtnActive" : "readerLangBtn"}
              onClick={() => switchSummaryLang("original")}
            >
              原文摘要
            </button>
          </div>
          <p>{summaryForLang(article, currentLang)}</p>
        </details>

        <details className="focusSection">
          <summary>评分</summary>
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
                    {DIMENSION_ROWS.filter(
                      (row): row is { key: DimensionKey; label: string } => row.key !== "overall",
                    )
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
        </details>

        {contentNotice ? <p className="contentPartialNotice">{contentNotice}</p> : null}

        <div className="articleContent content focusContent" dangerouslySetInnerHTML={{ __html: article.contentHtml }} />
      </article>

      <section
        className={drawerOpen ? "agentDrawer agentDrawerOpen" : "agentDrawer"}
        aria-label="文章助手"
        ref={drawerRef}
      >
        <button
          type="button"
          className="agentDrawerHandle"
          aria-expanded={drawerOpen}
          aria-controls="agent-drawer-body"
          onClick={() => setDrawerOpen((value) => !value)}
        >
          <span>文章助手</span>
          <span>{answer.trim().length > 0 ? "已有回答" : "总结、要点、解释选中、行动建议"}</span>
        </button>
        <motion.div
          id="agent-drawer-body"
          className="agentDrawerBody"
          aria-hidden={!drawerOpen}
          inert={!drawerOpen}
          animate={drawerOpen ? "open" : "closed"}
          initial={false}
          variants={{
            open: { opacity: 1, y: 0 },
            closed: { opacity: 0, y: 8 },
          }}
        >
          <div className="agentQuickActions" aria-label="快捷提问">
            {QUICK_ACTIONS.map((action) => (
              <button
                type="button"
                className="readerToolbarBtn"
                key={action.label}
                disabled={!drawerOpen || isAsking}
                onClick={() => void askAgent(action.question)}
              >
                {action.label}
              </button>
            ))}
          </div>
          <div className="agentDrawerAskRow">
            <textarea
              className="agentQuestion"
              value={question}
              disabled={!drawerOpen}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="问当前文章..."
              rows={3}
            />
            <button
              type="button"
              className="readerToolbarBtn readerToolbarBtnPrimary"
              disabled={!drawerOpen || question.trim().length === 0 || isAsking}
              onClick={() => void askAgent()}
            >
              {isAsking ? "生成中" : "询问"}
            </button>
          </div>
          {agentNotice ? <p className="agentNotice">{agentNotice}</p> : null}
          {agentError != null ? <p className="agentError">{agentError}</p> : null}
          {answer.trim().length > 0 ? <AgentMarkdown text={answer} /> : null}
        </motion.div>
      </section>
    </main>
  );
}
