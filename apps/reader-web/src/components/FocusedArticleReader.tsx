"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { Article, ArticleFeedbackType, DimensionKey } from "@/lib/articles/types";
import { ARTICLE_FEEDBACK_TYPES } from "@/lib/articles/types";
import { findCitationTarget, type SummaryLangId } from "@/lib/articles/service";
import { useTypewriterStream } from "@/lib/agent/typewriter";
import {
  createArticleAnnotation,
  getArticle,
  listArticleAnnotations,
  saveArticleFeedback,
  type ArticleAnnotation,
} from "@/lib/api/articles";
import { streamArticleAsk, type ArticleAskCitation } from "@/lib/api/client";
import { listClusters, listThemes } from "@/lib/api/intel";
import { applyHighlightMarksWithResolution } from "@/lib/articles/highlights";
import { selectionPreview, useArticleSelection } from "@/lib/articles/selection";
import { readCraftPreferences } from "@/lib/craft/preferences";
import { moveCommandIndex } from "@/lib/commandPalette";
import { AgentMarkdown } from "./AgentMarkdown";
import { AnimatedPanel } from "./AnimatedPanel";
import { ScoreRing, tierColorVar, tierLabel } from "./ScoreRing";
import { SkeletonBlock } from "./Skeleton";
import { emitToast } from "./Toast";
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
  { label: "定义", question: "请用简明中文解释本文中的关键术语与定义。" },
  { label: "简化", question: "请把这篇文章改写成更易懂的版本，保留关键数字与结论。" },
  { label: "反驳", question: "请站在批评者角度，反驳或挑战本文的核心论点，并给出证据缺口。" },
  { label: "闪卡", question: "请基于本文生成 5 张间隔复习闪卡（正面问题 / 背面答案）。" },
];

const FEEDBACK_OPTIONS: { type: ArticleFeedbackType; label: string }[] = [
  { type: "underrated", label: "低估" },
  { type: "overrated", label: "高估" },
  { type: "too_promotional", label: "营销过重" },
  { type: "low_density", label: "信息密度低" },
  { type: "outdated", label: "过时" },
  { type: "duplicate", label: "重复" },
  { type: "wrong_category", label: "分类错误" },
  { type: "other", label: "其他" },
];

function summaryForLang(article: Article, lang: SummaryLangId): string {
  const summary = lang === "original" ? article.summaryOriginal || article.summaryZh : article.summaryZh;
  return summary.trim() || "暂无摘要，评分完成后自动生成。";
}

function summaryLangPath(nextLang: SummaryLangId): string {
  const qs = new URLSearchParams(window.location.search);
  qs.set("lang", nextLang);
  return `${window.location.pathname}?${qs.toString()}`;
}

function normalizeFeedbackType(value: string | undefined): ArticleFeedbackType | null {
  return ARTICLE_FEEDBACK_TYPES.includes(value as ArticleFeedbackType)
    ? (value as ArticleFeedbackType)
    : null;
}

function initialFeedbackScore(article: Article): string {
  return String(article.myFeedback?.userScore ?? article.score?.overall ?? 50);
}

function translationLabel(article: Article): string {
  if (article.contentZhStatus === "succeeded") return "译文：已就绪";
  if (article.contentZhStatus === "queued" || article.contentZhStatus === "running") return "译文：生成中";
  if (article.contentZhStatus === "failed") return "译文：失败";
  return "译文：未翻译";
}

function translationStatusClassName(article: Article): string {
  return article.contentZhStatus === "failed"
    ? "focusStatusChip focusStatusChipDanger"
    : "focusStatusChip";
}

type TierStatusStyle = CSSProperties & {
  "--statusTierColor"?: string;
};

type DimensionBarStyle = CSSProperties & {
  "--dimensionValue"?: string;
  "--dimensionColor"?: string;
};

function normalizedDimensionValue(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function FocusedArticleReader({
  article,
  currentLang,
  returnHref,
  initialCitation,
}: {
  article: Article;
  currentLang: SummaryLangId;
  returnHref: string;
  initialCitation?: string;
}) {
  const [question, setQuestion] = useState("");
  const [agentError, setAgentError] = useState<string | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [askHistory, setAskHistory] = useState<Array<{ role: "user" | "assistant"; content: string }>>(
    [],
  );
  const [citations, setCitations] = useState<ArticleAskCitation[]>([]);
  const [related, setRelated] = useState<
    Array<{ kind: "theme" | "cluster"; label: string; href: string }>
  >([]);
  const [dualPane, setDualPane] = useState(false);
  const [dualPaneKind, setDualPaneKind] = useState<"notes" | "article">("notes");
  const [dualArticleId, setDualArticleId] = useState<number | null>(null);
  const [dualArticle, setDualArticle] = useState<Article | null>(null);
  const [dualArticleError, setDualArticleError] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [highlightColor, setHighlightColor] = useState("yellow");
  const [highlightTags, setHighlightTags] = useState("");
  const [bilingual, setBilingual] = useState(false);
  const [annotations, setAnnotations] = useState<ArticleAnnotation[]>([]);
  const [annotationsError, setAnnotationsError] = useState<string | null>(null);
  const [annotationSaveError, setAnnotationSaveError] = useState<string | null>(null);
  const retryAnnotationSaveRef = useRef<(() => void) | null>(null);
  const retryAnnotationSelectionRevisionRef = useRef<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [translatedHtml, setTranslatedHtml] = useState<string | null>(article.contentZh ?? null);
  const [showTranslation, setShowTranslation] = useState(false);
  const [feedbackScore, setFeedbackScore] = useState(() => initialFeedbackScore(article));
  const [feedbackType, setFeedbackType] = useState<ArticleFeedbackType | null>(() =>
    normalizeFeedbackType(article.myFeedback?.feedbackType),
  );
  const [feedbackReason, setFeedbackReason] = useState(article.myFeedback?.reason ?? "");
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [isSavingFeedback, setIsSavingFeedback] = useState(false);
  const [secondaryActionsOpen, setSecondaryActionsOpen] = useState(false);
  const [activeSecondaryActionIndex, setActiveSecondaryActionIndex] = useState(0);
  const router = useRouter();
  const drawerRef = useRef<HTMLElement | null>(null);
  const secondaryMenuRef = useRef<HTMLDivElement | null>(null);
  const secondaryMenuButtonRef = useRef<HTMLButtonElement | null>(null);
  const secondaryActionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const articleRef = useRef<HTMLElement | null>(null);
  const focusContentRef = useRef<HTMLDivElement | null>(null);
  const scoreDetailsRef = useRef<HTMLDetailsElement | null>(null);
  const feedbackPanelRef = useRef<HTMLDivElement | null>(null);
  const feedbackScoreInputRef = useRef<HTMLInputElement | null>(null);
  const answerRef = useRef<HTMLDivElement | null>(null);
  const askAbortRef = useRef<AbortController | null>(null);
  const showTranslationWhenReadyRef = useRef(false);
  const articleActions = useArticleActions(article, currentLang);
  const typewriter = useTypewriterStream();
  const {
    selectedText,
    hasSelection,
    selectionRect,
    settledAnchor,
    selectionRevision,
    clearSelection,
  } = useArticleSelection(articleRef, focusContentRef);
  useEffect(() => {
    if (
      retryAnnotationSelectionRevisionRef.current != null &&
      retryAnnotationSelectionRevisionRef.current !== selectionRevision
    ) {
      retryAnnotationSelectionRevisionRef.current = null;
      retryAnnotationSaveRef.current = null;
      setAnnotationSaveError(null);
    }
  }, [selectionRevision]);
  const revealedAnswer = typewriter.revealed;
  const answerVisible = revealedAnswer.trim().length > 0 || typewriter.isRevealing;
  const answerPending = isAsking && !answerVisible && agentError == null;
  const cursorVisible = isAsking || typewriter.isRevealing;
  const secondaryActions = [
    {
      key: "refresh",
      label: articleActions.isFetchingContent ? "刷新中" : "刷新全文",
      disabled: articleActions.isFetchingContent,
      run: () => void articleActions.refreshFullContent(),
    },
    {
      key: "candidate",
      label: article.starred ? "移出候选" : "加入候选",
      disabled: articleActions.isTogglingCandidate,
      run: () => void articleActions.toggleCandidate(),
    },
    {
      key: "project",
      label: article.project ? "已立项" : articleActions.isProjecting ? "立项中" : "立项",
      disabled: article.project || articleActions.isProjecting,
      run: () => void articleActions.enqueueProject(),
    },
    {
      key: "read",
      label: articleActions.isMarkingRead ? "标记中" : "标记已读",
      disabled: articleActions.isMarkingRead,
      run: () => void articleActions.markRead(),
    },
  ];

  function focusSecondaryAction(index: number) {
    window.requestAnimationFrame(() => secondaryActionRefs.current[index]?.focus());
  }

  function openSecondaryActions(index = 0) {
    setActiveSecondaryActionIndex(index);
    setSecondaryActionsOpen(true);
    focusSecondaryAction(index);
  }

  function closeSecondaryActions() {
    setSecondaryActionsOpen(false);
  }

  function runSecondaryAction(index: number) {
    const action = secondaryActions[index];
    if (!action || action.disabled) return;
    closeSecondaryActions();
    action.run();
  }

  useEffect(() => {
    function applyPrefs() {
      const prefs = readCraftPreferences();
      setDualPane(prefs.dualPane);
      setDualPaneKind(prefs.dualPaneKind);
      setDualArticleId(prefs.dualArticleId);
    }
    applyPrefs();
    window.addEventListener("ai-reader:craft-prefs", applyPrefs);
    return () => window.removeEventListener("ai-reader:craft-prefs", applyPrefs);
  }, []);

  const reloadDualArticle = useCallback(() => {
    if (!dualPane || dualPaneKind !== "article" || dualArticleId == null) {
      setDualArticle(null);
      return;
    }
    if (dualArticleId === article.id) {
      setDualArticle(null);
      return;
    }
    let active = true;
    setDualArticleError(null);
    getArticle(dualArticleId)
      .then((next) => {
        if (active) setDualArticle(next);
      })
      .catch((caught) => {
        if (active) {
          setDualArticle(null);
          setDualArticleError(caught instanceof Error ? caught.message : "加载对照文章失败");
        }
      });
    return () => {
      active = false;
    };
  }, [article.id, dualArticleId, dualPane, dualPaneKind]);

  useEffect(() => reloadDualArticle(), [reloadDualArticle]);

  const reloadAnnotations = useCallback(() => {
    let active = true;
    setAnnotationsError(null);
    listArticleAnnotations(article.id)
      .then((items) => {
        if (active) setAnnotations(items);
      })
      .catch((caught) => {
        if (active) setAnnotationsError(caught instanceof Error ? caught.message : "加载划线失败");
      });
    return () => {
      active = false;
    };
  }, [article.id]);

  useEffect(() => reloadAnnotations(), [reloadAnnotations]);

  useEffect(() => {
    let active = true;
    Promise.allSettled([listThemes(30), listClusters(20)]).then((results) => {
      if (!active) return;
      const next: Array<{ kind: "theme" | "cluster"; label: string; href: string }> = [];
      const themes = results[0].status === "fulfilled" ? results[0].value : [];
      const clusters = results[1].status === "fulfilled" ? results[1].value : [];
      for (const theme of themes) {
        if (!theme.articleIds.includes(article.id)) continue;
        next.push({
          kind: "theme",
          label: theme.label,
          href: `/?module=themes&sort=default&lang=zh`,
        });
        for (const relatedId of theme.articleIds) {
          if (relatedId === article.id) continue;
          next.push({
            kind: "theme",
            label: `${theme.label} → #${relatedId}`,
            href: `/read/${relatedId}?module=themes&sort=default&lang=zh`,
          });
          if (next.length >= 8) break;
        }
      }
      for (const cluster of clusters) {
        if (
          cluster.mainArticleId !== article.id &&
          !cluster.relatedArticleIds.includes(article.id)
        ) {
          continue;
        }
        next.push({
          kind: "cluster",
          label: `${cluster.label} (${cluster.size})`,
          href: `/read/${cluster.mainArticleId}?module=clusters&sort=default&lang=zh`,
        });
      }
      setRelated(next.slice(0, 10));
    });
    return () => {
      active = false;
    };
  }, [article.id]);

  useEffect(() => {
    askAbortRef.current?.abort();
    setTranslatedHtml(article.contentZh ?? null);
    setShowTranslation(false);
    showTranslationWhenReadyRef.current = false;
    setIsAsking(false);
    setAgentError(null);
    setAskHistory([]);
    setCitations([]);
    setFeedbackScore(initialFeedbackScore(article));
    setFeedbackType(normalizeFeedbackType(article.myFeedback?.feedbackType));
    setFeedbackReason(article.myFeedback?.reason ?? "");
    setFeedbackError(null);
    setIsSavingFeedback(false);
  }, [article.id]);

  useEffect(() => {
    setTranslatedHtml(article.contentZh ?? null);
    if (article.contentZh != null && article.contentZh.trim().length > 0 && showTranslationWhenReadyRef.current) {
      setTranslatedHtml(article.contentZh);
      setShowTranslation(true);
      showTranslationWhenReadyRef.current = false;
    } else if (article.contentZh == null || article.contentZh.trim().length === 0) {
      setShowTranslation(false);
    }
  }, [article.contentZh]);

  useEffect(() => {
    return () => {
      askAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const markdown = answerRef.current?.querySelector<HTMLElement>(".agentMarkdown");
    if (markdown != null) markdown.scrollTop = markdown.scrollHeight;
  }, [revealedAnswer, typewriter.isRevealing]);

  useDismissableLayer({
    enabled: drawerOpen,
    layerRef: drawerRef,
    onDismiss: () => setDrawerOpen(false),
  });

  useDismissableLayer({
    enabled: secondaryActionsOpen,
    layerRef: secondaryMenuRef,
    ignoreRefs: [secondaryMenuButtonRef],
    onDismiss: closeSecondaryActions,
    restoreFocusRef: secondaryMenuButtonRef,
  });

  async function askAgent(nextQuestion = question) {
    const trimmedQuestion = nextQuestion.trim();
    if (trimmedQuestion.length === 0) return;
    const abortController = new AbortController();

    askAbortRef.current?.abort();
    askAbortRef.current = abortController;
    setDrawerOpen(true);
    setQuestion(trimmedQuestion);
    setIsAsking(true);
    setAgentError(null);
    setCitations([]);
    typewriter.reset();

    const historyPayload = askHistory.slice(-6);
    let answerText = "";

    try {
      for await (const event of streamArticleAsk(
        article.id,
        {
          question: trimmedQuestion,
          selected_text: selectedText.trim() || undefined,
          history: historyPayload.length > 0 ? historyPayload : undefined,
        },
        { signal: abortController.signal },
      )) {
        if (event.type === "text" && event.text.length > 0) {
          answerText += event.text;
          typewriter.push(event.text);
        } else if (event.type === "citations") {
          setCitations(event.citations);
        }
      }
      if (answerText.trim().length > 0) {
        setAskHistory((current) =>
          [
            ...current,
            { role: "user" as const, content: trimmedQuestion },
            { role: "assistant" as const, content: answerText.trim() },
          ].slice(-6),
        );
      }
    } catch (error) {
      if (abortController.signal.aborted) return;
      setAgentError(articleAskErrorMessage(error));
    } finally {
      if (askAbortRef.current === abortController) {
        askAbortRef.current = null;
      }
      typewriter.finish();
      setIsAsking(false);
    }
  }

  function scrollToCitation(quote: string) {
    const root = articleRef.current;
    if (root == null || quote.trim().length === 0) return;
    root.querySelectorAll(".citationJumpFlash").forEach((node) => {
      node.classList.remove("citationJumpFlash");
    });
    const target = findCitationTarget(root, quote);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("citationJumpFlash");
      window.setTimeout(() => target.classList.remove("citationJumpFlash"), 1600);
      return;
    }
    const findInPage = (window as Window & { find?: (...args: unknown[]) => boolean }).find;
    if (typeof window !== "undefined" && typeof findInPage === "function") {
      try {
        window.getSelection()?.removeAllRanges();
        const found = findInPage(quote.slice(0, 80), false, false, true, false, false, false);
        if (found) return;
      } catch {
        // fall through to manual search
      }
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const text = node.textContent ?? "";
      const index = text.indexOf(quote.slice(0, Math.min(quote.length, 48)));
      if (index >= 0 && node.parentElement) {
        node.parentElement.scrollIntoView({ behavior: "smooth", block: "center" });
        node.parentElement.classList.add("citationJumpFlash");
        return;
      }
      node = walker.nextNode();
    }
  }

  useEffect(() => {
    if (!initialCitation?.trim()) return;
    const frame = window.requestAnimationFrame(() => scrollToCitation(initialCitation));
    return () => window.cancelAnimationFrame(frame);
  }, [article.id, initialCitation]);

  function cancelAsk() {
    askAbortRef.current?.abort();
  }

  function switchSummaryLang(nextLang: SummaryLangId) {
    if (nextLang === currentLang) return;
    router.push(summaryLangPath(nextLang), { scroll: false });
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
    } else {
      showTranslationWhenReadyRef.current = true;
    }
  }

  async function submitFeedback() {
    const userScore = Number(feedbackScore);
    if (!Number.isInteger(userScore) || userScore < 0 || userScore > 100) {
      setFeedbackError("请输入 0 到 100 的反馈分值。");
      return;
    }
    if (feedbackType == null) {
      setFeedbackError("请选择反馈类型。");
      return;
    }

    setIsSavingFeedback(true);
    setFeedbackError(null);
    try {
      const savedFeedback = await saveArticleFeedback(article.id, {
        userScore,
        feedbackType,
        reason: feedbackReason.trim(),
      });
      setFeedbackScore(String(savedFeedback.userScore));
      setFeedbackType(savedFeedback.feedbackType);
      setFeedbackReason(savedFeedback.reason);
      emitToast({ title: "反馈已保存", variant: "success" });
    } catch {
      setFeedbackError("反馈保存失败，请稍后重试。");
    } finally {
      setIsSavingFeedback(false);
    }
  }

  function openFeedbackPanel() {
    scoreDetailsRef.current?.setAttribute("open", "");
    feedbackPanelRef.current?.scrollIntoView({ block: "center" });
    window.requestAnimationFrame(() => feedbackScoreInputRef.current?.focus());
  }

  const score = article.score;
  const contentNotice = articleContentNotice(article);
  const agentNotice = articleAgentNotice(article);
  const baseHtml = showTranslation && translatedHtml ? translatedHtml : article.contentHtml;
  const highlightApplication = useMemo(
    () =>
      applyHighlightMarksWithResolution(
        baseHtml,
        annotations.map((item) => ({
          id: item.id,
          selectedText: item.selectedText || item.content,
          color: item.color,
          anchor: item.anchor,
        })),
      ),
    [annotations, baseHtml],
  );
  const displayedHtml = highlightApplication.html;
  const unresolvedAnnotations = annotations.filter((item) =>
    highlightApplication.unresolvedAnnotationIds.includes(item.id),
  );
  const scoreStatusStyle: TierStatusStyle | undefined = score
    ? { "--statusTierColor": `var(${tierColorVar(score.tier, score.overall)})` }
    : undefined;

  return (
    <motion.main
      className={dualPane ? "focusReader focusReaderDualPane" : "focusReader"}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.19, ease: "easeOut" }}
    >
      <div className="focusReaderLayout">
        <div className="focusReaderPrimary">
          <header className="focusTopbar">
        <Link className="readerToolbarBtn" href={returnHref} prefetch={false}>
          返回工作台
        </Link>
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
          <div className="focusOverflowMenu" ref={secondaryMenuRef}>
            <button
              ref={secondaryMenuButtonRef}
              type="button"
              className="readerToolbarBtn focusOverflowMenuButton"
              aria-haspopup="menu"
              aria-expanded={secondaryActionsOpen}
              aria-controls="focus-overflow-menu"
              aria-label="更多文章操作"
              onClick={() => {
                if (secondaryActionsOpen) closeSecondaryActions();
                else openSecondaryActions();
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown" || event.key === "Home") {
                  event.preventDefault();
                  openSecondaryActions(0);
                } else if (event.key === "ArrowUp" || event.key === "End") {
                  event.preventDefault();
                  openSecondaryActions(Math.max(secondaryActions.length - 1, 0));
                }
              }}
            >
              ⋯
            </button>
            <AnimatePresence initial={false}>
              {secondaryActionsOpen ? (
                <AnimatedPanel
                  key="focus-overflow-menu"
                  id="focus-overflow-menu"
                  variant="popover"
                  className="focusOverflowPopover"
                  role="menu"
                  aria-label="更多文章操作"
                  onKeyDown={(event) => {
                    if (event.key === "ArrowDown") {
                      event.preventDefault();
                      setActiveSecondaryActionIndex((index) => {
                        const next = moveCommandIndex(index, 1, secondaryActions.length);
                        focusSecondaryAction(next);
                        return next;
                      });
                    } else if (event.key === "ArrowUp") {
                      event.preventDefault();
                      setActiveSecondaryActionIndex((index) => {
                        const next = moveCommandIndex(index, -1, secondaryActions.length);
                        focusSecondaryAction(next);
                        return next;
                      });
                    } else if (event.key === "Home") {
                      event.preventDefault();
                      setActiveSecondaryActionIndex(0);
                      focusSecondaryAction(0);
                    } else if (event.key === "End") {
                      event.preventDefault();
                      const lastIndex = Math.max(secondaryActions.length - 1, 0);
                      setActiveSecondaryActionIndex(lastIndex);
                      focusSecondaryAction(lastIndex);
                    } else if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      runSecondaryAction(activeSecondaryActionIndex);
                    }
                  }}
                >
                  {secondaryActions.map((action, index) => (
                    <button
                      ref={(element) => {
                        secondaryActionRefs.current[index] = element;
                      }}
                      key={action.key}
                      type="button"
                      className="focusOverflowOption"
                      role="menuitem"
                      disabled={action.disabled}
                      tabIndex={index === activeSecondaryActionIndex ? 0 : -1}
                      onFocus={() => setActiveSecondaryActionIndex(index)}
                      onClick={() => runSecondaryAction(index)}
                    >
                      {action.label}
                    </button>
                  ))}
                </AnimatedPanel>
              ) : null}
            </AnimatePresence>
          </div>
        </div>
      </header>

      <section className="focusStatusBar" aria-label="阅读状态">
        <span className="focusStatusChip">{article.contentStatus === "partial" ? "正文：片段" : "正文：完整"}</span>
        <span
          className={score ? "focusStatusChip focusStatusChipScored" : "focusStatusChip"}
          style={scoreStatusStyle}
        >
          {score ? "评分：已评分" : "评分：未评分"}
        </span>
        <span className={translationStatusClassName(article)}>{translationLabel(article)}</span>
        <button type="button" className="focusStatusChip focusStatusAction" onClick={openFeedbackPanel}>
          反馈校准
        </button>
      </section>

      {articleActions.actionError ? (
        <section className="readerActionError" role="alert">
          <p>{articleActions.actionError}</p>
          {articleActions.canRetryAction ? (
            <button type="button" className="readerToolbarBtn" onClick={articleActions.retryLastAction}>
              重试操作
            </button>
          ) : null}
        </section>
      ) : null}

      {article.contentZhStatus === "failed" ? (
        <section className="focusTranslationAlert" role="alert" aria-label="译文生成失败">
          <div>
            <strong>译文生成失败</strong>
            <p>可重新提交全文翻译任务，成功后将自动切换到译文。</p>
          </div>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={articleActions.isTranslating}
            onClick={() => void toggleTranslation()}
          >
            ↻ 重试翻译
          </button>
        </section>
      ) : article.contentZhStatus === "queued" || article.contentZhStatus === "running" ? (
        <section
          className="focusTranslationAlert focusTranslationAlertPending"
          role="status"
          aria-label="译文生成中"
        >
          <span className="focusTranslationSpinner" aria-hidden="true" />
          <div>
            <strong>译文生成中</strong>
            <p>任务完成后会自动切换到译文。</p>
          </div>
        </section>
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
          <p className="focusSummaryQuote">{summaryForLang(article, currentLang)}</p>
        </details>

        <details className="focusSection" ref={scoreDetailsRef}>
          <summary>评分</summary>
          {score ? (
            <>
              <div className="scoreOverview">
                <ScoreRing value={score.overall} tier={score.tier} size={46} />
                <div>
                  <strong className="scoreOverviewTier">{tierLabel(score.tier) ?? "未分层"}</strong>
                  <p className="scoreReason">
                    <span className="scoreReasonLabel">总评</span>
                    {score.reason.trim() || "暂无评分理由。"}
                  </p>
                </div>
              </div>
              <div className="dimensionBars" aria-label="评分维度">
                {DIMENSION_ROWS.filter(
                  (row): row is { key: DimensionKey; label: string } => row.key !== "overall",
                ).map((row) => {
                  const value = normalizedDimensionValue(score.dimensions[row.key] ?? null);
                  const style: DimensionBarStyle | undefined =
                    value == null
                      ? undefined
                      : {
                          "--dimensionValue": `${value}%`,
                          "--dimensionColor": `var(${tierColorVar(null, value)})`,
                        };
                  return (
                    <div className="dimensionBarRow" key={row.key}>
                      <span className="dimensionBarLabel">{row.label}</span>
                      <span
                        className="dimensionBarTrack"
                        role="progressbar"
                        aria-label={row.label}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={value ?? undefined}
                        aria-valuetext={value == null ? "未评分" : undefined}
                      >
                        <span className="dimensionBarFill" style={style} />
                      </span>
                      <span className="dimensionBarValue">{value ?? "—"}</span>
                    </div>
                  );
                })}
              </div>
              <p className="scoreRiskHint">风险·不确定维度越高代表越需要谨慎，不按普通高分理解。</p>
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
            <p className="scoreMissing">未评分。评分完成后将生成摘要、分数和理由。</p>
          )}
          <div className="scoreFeedbackPanel" aria-label="反馈校准" ref={feedbackPanelRef}>
            <div className="scoreFeedbackHeader">
              <p className="scoreFeedbackTitle">反馈校准</p>
              <label className="scoreFeedbackInputLabel">
                我的分数
                <input
                  ref={feedbackScoreInputRef}
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  value={feedbackScore}
                  onChange={(event) => setFeedbackScore(event.target.value)}
                />
              </label>
            </div>
            <div className="scoreFeedbackChips" role="group" aria-label="反馈类型">
              {FEEDBACK_OPTIONS.map((option) => (
                <button
                  key={option.type}
                  type="button"
                  className={
                    option.type === feedbackType
                      ? "scoreFeedbackChip scoreFeedbackChipActive"
                      : "scoreFeedbackChip"
                  }
                  aria-pressed={option.type === feedbackType}
                  onClick={() => setFeedbackType(option.type)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <label className="scoreFeedbackReason">
              备注
              <textarea
                value={feedbackReason}
                rows={2}
                onChange={(event) => setFeedbackReason(event.target.value)}
              />
            </label>
            {feedbackError ? <p className="readerActionError scoreFeedbackError">{feedbackError}</p> : null}
            <button
              type="button"
              className="readerToolbarBtn readerToolbarBtnPrimary"
              disabled={isSavingFeedback}
              onClick={() => void submitFeedback()}
            >
              {isSavingFeedback ? "保存中" : "保存反馈"}
            </button>
          </div>
        </details>

        {contentNotice ? <p className="contentPartialNotice">{contentNotice}</p> : null}
        {highlightApplication.unresolvedAnnotationIds.length > 0 ? (
          <>
            <p className="contentPartialNotice" role="status">
              有 {highlightApplication.unresolvedAnnotationIds.length} 条已保存划线因内容变化未安全定位；原笔记仍保留，请核对原文后重新标注。
            </p>
            <details className="unresolvedAnnotations">
              <summary>查看保留的未定位标注（{unresolvedAnnotations.length}）</summary>
              <ul>
                {unresolvedAnnotations.map((item) => (
                  <li key={item.id}>
                    {item.selectedText ? <p>原选区：{item.selectedText}</p> : null}
                    <p>{item.content}</p>
                  </li>
                ))}
              </ul>
            </details>
          </>
        ) : null}

        <div className="articleListActions" style={{ marginBottom: 8 }}>
          <button
            type="button"
            className="readerToolbarBtn"
            onClick={() => setBilingual((value) => !value)}
            disabled={!translatedHtml}
          >
            {bilingual ? "关闭对照" : "原文/译文对照"}
          </button>
        </div>

        {bilingual && translatedHtml ? (
          <div className="bilingualSplit">
            <div>
              <h3 className="workbenchRibbonMuted">原文</h3>
              <div
                className="articleContent content focusContent"
                dangerouslySetInnerHTML={{ __html: article.contentHtml }}
              />
            </div>
            <div>
              <h3 className="workbenchRibbonMuted">译文</h3>
              <div
                className="articleContent content focusContent"
                dangerouslySetInnerHTML={{ __html: translatedHtml }}
              />
            </div>
          </div>
        ) : (
          <div ref={focusContentRef} className="articleContent content focusContent" dangerouslySetInnerHTML={{ __html: displayedHtml }} />
        )}
      </article>
        </div>

        {dualPane && dualPaneKind === "notes" ? (
          <aside className="focusedArticleNotes" aria-label="笔记双栏">
            <h2>笔记</h2>
            <p className="workbenchRibbonMuted">双栏模式：文章 + 笔记。选区高亮仍会保存到私有标注。</p>
            {annotationsError ? <p className="adminConsoleError">加载已有划线失败：{annotationsError}<button type="button" className="readerToolbarBtn" onClick={reloadAnnotations}>重试</button></p> : null}
            <textarea
              className="agentQuestion"
              rows={12}
              value={noteDraft}
              onChange={(event) => setNoteDraft(event.target.value)}
              placeholder="边读边记…"
            />
            <button
              type="button"
              className="readerToolbarBtn readerToolbarBtnPrimary"
              disabled={noteDraft.trim().length === 0}
              onClick={() => {
                const save = () => {
                  void createArticleAnnotation(article.id, {
                    content: noteDraft.trim(),
                    selectedText: selectedText || null,
                    color: highlightColor,
                    anchor: settledAnchor ?? undefined,
                  })
                    .then((created) => {
                      setAnnotations((current) => [created, ...current]);
                      setNoteDraft("");
                      setAnnotationSaveError(null);
                      retryAnnotationSaveRef.current = null;
                      retryAnnotationSelectionRevisionRef.current = null;
                      emitToast({ title: "笔记已保存", variant: "success" });
                    })
                    .catch((error) => {
                      const message = error instanceof Error ? error.message : "笔记保存失败";
                      setAnnotationSaveError(message);
                      retryAnnotationSaveRef.current = save;
                      retryAnnotationSelectionRevisionRef.current = null;
                      emitToast({ title: message, variant: "error" });
                    });
                };
                save();
              }}
            >
              保存笔记
            </button>
            {annotationSaveError ? (
              <p className="adminConsoleError" role="alert">
                {annotationSaveError}
                <button
                  type="button"
                  className="readerToolbarBtn"
                  onClick={() => retryAnnotationSaveRef.current?.()}
                >
                  重试保存
                </button>
              </p>
            ) : null}
          </aside>
        ) : null}

        {dualPane && dualPaneKind === "article" ? (
          <aside className="focusedArticleNotes dualArticlePane" aria-label="对照文章">
            <h2>对照阅读</h2>
            {dualArticleError ? (
              <p className="adminConsoleError">加载对照文章失败：{dualArticleError}<button type="button" className="readerToolbarBtn" onClick={reloadDualArticle}>重试</button></p>
            ) : dualArticle == null ? (
              <p className="workbenchRibbonMuted">在「阅读工艺」设置对照文章 ID，或 ⌘K 打开工艺面板。</p>
            ) : (
              <>
                <p className="workbenchRibbonMuted">
                  #{dualArticle.id} ·{" "}
                  <Link href={`/read/${dualArticle.id}?module=all&sort=default&lang=zh`} prefetch={false}>
                    单独打开
                  </Link>
                </p>
                <h3 className="dailyIntelCardTitle">{dualArticle.title}</h3>
                <div
                  className="articleContent content focusContent dualArticleBody"
                  dangerouslySetInnerHTML={{ __html: dualArticle.contentHtml }}
                />
              </>
            )}
          </aside>
        ) : null}
      </div>

      {selectionRect && hasSelection && !drawerOpen ? (
        <div
          className="selectionPopover"
          role="toolbar"
          aria-label="选中文字操作"
          onMouseDown={(event) => event.preventDefault()}
          onPointerDown={(event) => event.preventDefault()}
          style={{
            top: Math.max(8, selectionRect.top - 8),
            left: selectionRect.left + selectionRect.width / 2,
          }}
        >
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => void askAgent("请解释我选中的这段内容。")}
          >
            解释选中
          </button>
          <label className="selectionColorPicker">
            <span className="visuallyHidden">划线颜色</span>
            <select
              value={highlightColor}
              onChange={(event) => setHighlightColor(event.target.value)}
              onMouseDown={(event) => event.stopPropagation()}
            >
              <option value="yellow">黄</option>
              <option value="green">绿</option>
              <option value="blue">蓝</option>
              <option value="pink">粉</option>
              <option value="orange">橙</option>
              <option value="purple">紫</option>
            </select>
          </label>
          <input
            className="selectionTagInput"
            value={highlightTags}
            onChange={(event) => setHighlightTags(event.target.value)}
            onMouseDown={(event) => event.stopPropagation()}
            placeholder="标签,逗号分隔"
          />
          <button
            type="button"
            onMouseDown={(event) => event.preventDefault()}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => {
              const text = selectedText.trim();
              if (!text) return;
              const tags = highlightTags
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean);
              const save = () => {
                void createArticleAnnotation(article.id, {
                  content: text,
                  selectedText: text,
                  type: "annotation",
                  color: highlightColor,
                  tags,
                  anchor: settledAnchor ?? undefined,
                })
                  .then((created) => {
                    setAnnotations((current) => [created, ...current]);
                    setAnnotationSaveError(null);
                    retryAnnotationSaveRef.current = null;
                    retryAnnotationSelectionRevisionRef.current = null;
                    emitToast({ title: "已保存划线", variant: "success" });
                    clearSelection();
                  })
                  .catch((error: unknown) => {
                    const message = error instanceof Error ? error.message : "划线保存失败";
                    setAnnotationSaveError(message);
                    retryAnnotationSaveRef.current = save;
                    retryAnnotationSelectionRevisionRef.current = selectionRevision;
                    emitToast({ title: "划线保存失败", body: message, variant: "error" });
                  });
              };
              save();
            }}
          >
            保存划线
          </button>
          {annotationSaveError ? (
            <p className="adminConsoleError" role="alert">
              {annotationSaveError}
              <button
                type="button"
                className="readerToolbarBtn"
                onMouseDown={(event) => event.preventDefault()}
                onPointerDown={(event) => event.preventDefault()}
                onClick={() => retryAnnotationSaveRef.current?.()}
              >
                重试保存
              </button>
            </p>
          ) : null}
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
            {isAsking ? (
              <button type="button" className="readerToolbarBtn" onClick={cancelAsk}>
                停止
              </button>
            ) : null}
          </div>
          {agentNotice ? <p className="agentNotice">{agentNotice}</p> : null}
          {agentError != null ? <p className="agentError">{agentError}</p> : null}
          {answerPending ? (
            <div className="agentAnswerPending" aria-label="答案生成中" aria-live="polite">
              <SkeletonBlock className="skeletonLine" width="86%" />
              <SkeletonBlock className="skeletonLine" width="64%" />
            </div>
          ) : null}
          {answerVisible ? (
            <div className="agentAnswer" ref={answerRef}>
              <AgentMarkdown
                text={revealedAnswer}
                trailing={cursorVisible ? <span className="typewriterCursor">▍</span> : null}
              />
              {citations.length > 0 ? (
                <div className="agentCitations" aria-label="原文引用">
                  {citations.map((citation) => (
                    <button
                      key={`${citation.startHint ?? "x"}:${citation.quote}`}
                      type="button"
                      className="agentCitationBtn"
                      title={citation.quote}
                      onClick={() => scrollToCitation(citation.quote)}
                    >
                      “{citation.quote.length > 42 ? `${citation.quote.slice(0, 42)}…` : citation.quote}”
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </motion.div>
      </section>

      {related.length > 0 ? (
        <aside className="focusRelatedRail" aria-label="相关主题与故事线">
          <h2>相关跳转</h2>
          <ul>
            {related.map((item) => (
              <li key={`${item.kind}-${item.label}-${item.href}`}>
                <Link href={item.href} prefetch={false}>
                  <span className="workbenchRibbonMuted">{item.kind}</span> {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </aside>
      ) : null}
    </motion.main>
  );
}
