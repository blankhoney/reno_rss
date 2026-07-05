"use client";

import { useEffect, useRef, useState } from "react";
import type { Article } from "@/lib/articles/types";
import type { SummaryLangId } from "@/lib/articles/service";
import {
  enqueueFetchContentJob,
  pollJobUntilTerminal,
  requestArticleTranslation,
  updateArticleState,
  type ApiJob,
} from "@/lib/api/articles";
import { emitToast, type ToastAction, type ToastVariant } from "./Toast";

type ActionKey = "fetchContent" | "translate" | "candidate" | "project" | "read";

type ActionLink = ToastAction;
type ActionResult =
  | string
  | {
      message: string;
      action?: ActionLink | null;
      variant?: ToastVariant;
    };

export const ARTICLE_DATA_CHANGED_EVENT = "ai-reader:articles-changed";

function savedHref(entryId: number, lang: SummaryLangId): string {
  const qs = new URLSearchParams({
    module: "starred",
    sort: "default",
    lang,
    article: String(entryId),
  });
  return `/?${qs.toString()}`;
}

function resultString(result: unknown, key: string): string | null {
  if (result === null || typeof result !== "object" || Array.isArray(result)) return null;
  const value = (result as Record<string, unknown>)[key];
  return typeof value === "string" ? value : null;
}

export function contentFetchJobMessage(job: ApiJob): string {
  if (job.status === "failed") return "全文抓取失败，请打开原文阅读";

  const outcome = resultString(job.result, "outcome");
  const quality = resultString(job.result, "content_quality") ?? resultString(job.result, "quality");
  if (outcome === "applied" && quality === "full") {
    return "全文已刷新，已切换到较完整正文";
  }
  if (outcome === "applied") {
    return "已获取到更多内容，但当前仍可能只有 RSS 片段";
  }
  if (outcome === "rejected") {
    return "源站返回错误页或登录墙，当前仍显示 RSS 片段";
  }
  if (outcome === "unchanged" || outcome === "fallback") {
    return "已尝试刷新全文，当前仍可能只有 RSS 片段";
  }
  return "全文刷新请求已完成";
}

export function translationJobMessage(job: ApiJob): string {
  if (job.status === "failed") return "全文翻译失败，请稍后重试";
  return "全文翻译已完成";
}

function articleActionErrorMessage(error: string): string {
  if (error === "article_not_candidate") return "请先加入候选再立项";
  if (error === "entry_not_found") return "文章不存在或不在当前 Miniflux 实例";
  if (error === "fetch_content_failed") return "全文抓取失败，请打开原文阅读";
  return error.trim() || "操作失败";
}

function dispatchArticleDataChanged(articleId: number) {
  window.dispatchEvent(new CustomEvent(ARTICLE_DATA_CHANGED_EVENT, { detail: { articleId } }));
}

function normalizeActionResult(result: ActionResult): {
  message: string;
  action?: ActionLink | null;
  variant?: ToastVariant;
} {
  return typeof result === "string" ? { message: result } : result;
}

export function useArticleActions(article: Article | null, currentLang: SummaryLangId) {
  const [pendingAction, setPendingAction] = useState<ActionKey | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const actionAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    actionAbortRef.current?.abort();
    setPendingAction(null);
    setActionError(null);
  }, [article?.id]);

  useEffect(() => {
    return () => {
      actionAbortRef.current?.abort();
    };
  }, []);

  async function run(action: ActionKey, request: (signal: AbortSignal) => Promise<ActionResult>) {
    if (article == null || pendingAction != null) return;
    const abortController = new AbortController();
    actionAbortRef.current?.abort();
    actionAbortRef.current = abortController;
    setPendingAction(action);
    setActionError(null);
    try {
      const result = normalizeActionResult(await request(abortController.signal));
      if (abortController.signal.aborted) return;
      emitToast({
        title: result.message,
        variant: result.variant ?? "success",
        action: result.action ?? null,
      });
      dispatchArticleDataChanged(article.id);
    } catch (error) {
      if (isAbortError(error)) return;
      const raw = error instanceof Error ? error.message : "操作失败";
      setActionError(articleActionErrorMessage(raw));
    } finally {
      if (actionAbortRef.current === abortController) {
        actionAbortRef.current = null;
      }
      setPendingAction(null);
    }
  }

  return {
    actionError,
    isFetchingContent: pendingAction === "fetchContent",
    isTranslating: pendingAction === "translate",
    isTogglingCandidate: pendingAction === "candidate",
    isProjecting: pendingAction === "project",
    isMarkingRead: pendingAction === "read",
    refreshFullContent: () =>
      run("fetchContent", async (signal) => {
        if (article == null) return "";
        const created = await enqueueFetchContentJob(article.id, { signal });
        const job = await pollJobUntilTerminal(created.jobId, { signal });
        return contentFetchJobMessage(job);
      }),
    translateFullText: async () => {
      if (article == null || pendingAction != null) return null;
      const abortController = new AbortController();
      actionAbortRef.current?.abort();
      actionAbortRef.current = abortController;
      setPendingAction("translate");
      setActionError(null);
      try {
        const requested = await requestArticleTranslation(article.id, { signal: abortController.signal });
        if (abortController.signal.aborted) return null;
        if (requested.contentZh != null) {
          emitToast({ title: "已切换到中文译文", variant: "success" });
          dispatchArticleDataChanged(article.id);
          return requested.contentZh;
        }
        if (requested.jobId == null) {
          emitToast({ title: "全文翻译请求已提交", variant: "success" });
          return null;
        }
        const job = await pollJobUntilTerminal(requested.jobId, {
          intervalMs: 1000,
          maxAttempts: 60,
          signal: abortController.signal,
        });
        if (abortController.signal.aborted) return null;
        emitToast({
          title: translationJobMessage(job),
          variant: job.status === "failed" ? "error" : "success",
        });
        dispatchArticleDataChanged(article.id);
        if (job.status !== "succeeded") return null;
        return null;
      } catch (error) {
        if (isAbortError(error)) return null;
        const raw = error instanceof Error ? error.message : "操作失败";
        setActionError(articleActionErrorMessage(raw));
        return null;
      } finally {
        if (actionAbortRef.current === abortController) {
          actionAbortRef.current = null;
        }
        setPendingAction(null);
      }
    },
    toggleCandidate: () =>
      run("candidate", async () => {
        if (article == null) return "";
        await updateArticleState(article.id, { saved: !article.starred });
        return article.starred ? "已移出候选" : "已加入候选";
      }),
    enqueueProject: () =>
      run("project", async () => {
        if (article == null) return "";
        await updateArticleState(article.id, { saved: true });
        return {
          message: "已加入候选",
          action: { href: savedHref(article.id, currentLang), label: "查看候选" },
        };
      }),
    markRead: () =>
      run("read", async () => {
        if (article == null) return "";
        await updateArticleState(article.id, { status: "read", readProgress: 1 });
        return "已标记为已读";
      }),
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
