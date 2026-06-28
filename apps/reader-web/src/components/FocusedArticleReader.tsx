"use client";

import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { Article, DimensionKey } from "@/lib/articles/types";
import type { SummaryLangId } from "@/lib/articles/service";
import { createThinkTagFilter } from "@/lib/agent/stream";
import { useTypewriterStream } from "@/lib/agent/typewriter";
import { streamArticleAsk } from "@/lib/api/client";
import { selectionPreview, useArticleSelection } from "@/lib/articles/selection";
import { AgentMarkdown } from "./AgentMarkdown";
import { ScoreBadge } from "./ScoreBadge";
import { ThemeToggle } from "./ThemeToggle";
import { articleAskErrorMessage } from "./articleAsk";
import { articleAgentNotice, articleContentNotice } from "./articleContentNotice";
import { useArticleActions } from "./useArticleActions";
import { useDismissableLayer } from "./useDismissableLayer";

const DIMENSION_ROWS: { key: DimensionKey | "overall"; label: string }[] = [
  { key: "overall", label: "总分" },
  { key: "topic_relevance", label: "主题相关性" },
  { key: "information_density", label: "信息密度" },
  { key: "source_quality", label: "来源质量" },
  { key: "novelty", label: "新颖度" },
  { key: "timeliness", label: "时效性" },
  { key: "actionability", label: "可执行性" },
  { key: "reading_cost_fit", label: "阅读成本" },
  { key: "risk_uncertainty", label: "风险·不确定" },
];

const QUICK_ACTIONS = [
  { label: "总结", question: "请总结这篇文章的核心内容。" },
  { label: "要点", question: "请提炼这篇文章最重要的 5 个要点。" },
  { label: "解释选中", question: "请解释我选中的这段内容。", requiresSelection: true },
  { label: "行动建议", question: "基于这篇文章，给出可执行的行动建议。" },
];

function summaryForLang(article: Article, lang: SummaryLangId): string {
  const summary = lang === "original" ? article.summaryOriginal || article.summaryZh : article.summaryZh;
  return summary.trim() || "暂无摘要，可在管理控制台完成评分后生成";
}

function switchSummaryLang(nextLang: SummaryLangId) {
  const qs = new URLSearchParams(window.location.search);
  qs.set("lang", nextLang);
  window.location.search = qs.toString();
}

function tierLabel(tier: string | undefined): string {
  if (tier === "must_read") return "必读";
  if (tier === "read") return "推荐";
  if (tier === "skim") return "略读";
  if (tier === "skip") return "跳过";
  return tier ?? "未分层";
}

function translationLabel(article: Article): string {
  if (article.contentZhStatus === "succeeded") return "译文：已就绪";
  if (article.contentZhStatus === "queued" || article.contentZhStatus === "running") return "译文：生成中";
  if (article.contentZhStatus === "failed") return "译文：失败";
  return "译文：未翻译";
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
  const [agentError, setAgentError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [translatedHtml, setTranslatedHtml] = useState<string | null>(article.contentZh ?? null);
  const [showTranslation, setShowTranslation] = useState(false);
  const drawerRef = useRef<HTMLElement | null>(null);
  const articleRef = useRef<HTMLElement | null>(null);
  const articleActions = useArticleActions(article, currentLang);
  const typewriter = useTypewriterStream();
  const { selectedText, hasSelection, selectionRect, clearSelection } = useArticleSelection(articleRef);

  useEffect(() => {
    setTranslatedHtml(article.contentZh ?? null);
    setShowTranslation(false);
  }, [article.id, article.contentZh]);

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
    setAgentError(null);
    typewriter.reset();

    try {
      const thinkFilter = createThinkTagFilter();
      for await (const chunk of streamArticleAsk(article.id, {
        question: trimmedQuestion,
        selected_text: selectedText.trim() || undefined,
      })) {
        const text = thinkFilter.push(chunk);
        if (text.length > 0) typewriter.push(text);
      }
      const finalText = thinkFilter.flush();
      if (finalText.length > 0) typewriter.push(finalText);
    } catch (error) {
      setAgentError(articleAskErrorMessage(error));
    } finally {
      typewriter.finish();
      setIsAsking(false);
    }
  }

  async function toggleTranslation() {
    if (showTranslation) {
      setShowTranslation(false);
      return;
    }
    if (translatedHtml != null && translatedHtml.trim().length > 0) {
      setShowTranslation(true);
      return;
    }

    const nextTranslatedHtml = await articleActions.translateFullText();
    if (nextTranslatedHtml != null) {
      setTranslatedHtml(nextTranslatedHtml);
      setShowTranslation(true);
    }
  }

  const score = article.score;
  const contentNotice = articleContentNotice(article);
  const agentNotice = articleAgentNotice(article);
  const displayedHtml = showTranslation && translatedHtml ? translatedHtml : article.contentHtml;
  const revealedAnswer = typewriter.revealed;
  const answerVisible = revealedAnswer.trim().length > 0 || typewriter.isRevealing;

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
            disabled={articleActions.isTranslating}
            onClick={() => void toggleTranslation()}
          >
            {showTranslation ? "看原文" : articleActions.isTranslating ? "翻译中" : "翻译全文"}
          </button>
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
        <ThemeToggle />
      </header>

      <section className="focusStatusBar" aria-label="阅读状态">
        <span>{article.contentStatus === "partial" ? "正文：片段" : "正文：完整"}</span>
        <span>{score ? "评分：已评分" : "评分：未评分"}</span>
        <span>{translationLabel(article)}</span>
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

      <article className="focusArticle" ref={articleRef}>
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
                <ScoreBadge label="层级" value={tierLabel(score.tier)} />
                {DIMENSION_ROWS.map((row) => {
                  const value =
                    row.key === "overall" ? score.overall : (score.dimensions[row.key] ?? null);
                  return <ScoreBadge key={row.key} label={row.label} value={value} />;
                })}
              </div>
              <p className="scoreRiskHint">风险·不确定维度越高代表越需要谨慎，不按普通高分理解。</p>
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
            <p className="scoreMissing">未评分。可在管理控制台创建评分批次生成摘要、分数和理由。</p>
          )}
        </details>

        {contentNotice ? <p className="contentPartialNotice">{contentNotice}</p> : null}

        <div className="articleContent content focusContent" dangerouslySetInnerHTML={{ __html: displayedHtml }} />
      </article>

      {selectionRect && hasSelection ? (
        <div
          className="selectionPopover"
          role="toolbar"
          aria-label="选中文字操作"
          style={{
            top: Math.max(8, selectionRect.top - 8),
            left: selectionRect.left + selectionRect.width / 2,
          }}
        >
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => void askAgent("请解释我选中的这段内容。")}
          >
            解释选中
          </button>
        </div>
      ) : null}

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
          <span>{revealedAnswer.trim().length > 0 ? "已有回答" : "总结、要点、解释选中、行动建议"}</span>
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
          {hasSelection ? (
            <div className="agentSelectionChip">
              <span>已选中：{selectionPreview(selectedText)}</span>
              <button type="button" onClick={clearSelection} aria-label="清除选中内容">
                ×
              </button>
            </div>
          ) : null}
          <div className="agentQuickActions" aria-label="快捷提问">
            {QUICK_ACTIONS.map((action) => (
              <button
                type="button"
                className="readerToolbarBtn"
                key={action.label}
                disabled={!drawerOpen || isAsking || (action.requiresSelection === true && !hasSelection)}
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
          {answerVisible ? (
            <div className="agentAnswer">
              <AgentMarkdown text={revealedAnswer} />
              {isAsking || typewriter.isRevealing ? <span className="typewriterCursor">▍</span> : null}
            </div>
          ) : null}
        </motion.div>
      </section>
    </main>
  );
}
