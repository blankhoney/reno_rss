"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Article } from "@/lib/articles/types";
import type { SummaryLangId } from "@/lib/articles/service";
import type { ArticleContentFetchResult } from "@/lib/articles/contentQuality";
import {
  enqueueFetchContentJob,
  getArticle,
  pollJobUntilTerminal,
  requestArticleTranslation,
  updateArticleState,
  type ApiJob,
} from "@/lib/api/articles";

type ActionKey = "fetchContent" | "translate" | "candidate" | "project" | "read";

type ActionLink = {
  href: string;
  label: string;
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

export function contentFetchResultMessage(result: ArticleContentFetchResult): string {
  if (result.outcome === "applied" && result.quality === "full") {
    return "全文已刷新，已切换到较完整正文";
  }
  if (result.outcome === "applied") {
    return "已获取到更多内容，但当前仍可能只有 RSS 片段";
  }
  if (result.outcome === "rejected") {
    return "源站返回错误页或登录墙，当前仍显示 RSS 片段";
  }
  if (result.outcome === "unchanged") {
    return "源站没有返回更完整正文，当前仍显示已有内容";
  }
  return "全文抓取失败，请打开原文阅读";
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

export function useArticleActions(article: Article | null, currentLang: SummaryLangId) {
  const router = useRouter();
  const [pendingAction, setPendingAction] = useState<ActionKey | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLink, setActionLink] = useState<ActionLink | null>(null);

  useEffect(() => {
    setPendingAction(null);
    setActionMessage(null);
    setActionError(null);
    setActionLink(null);
  }, [article?.id]);

  async function run(action: ActionKey, request: () => Promise<string>) {
    if (article == null || pendingAction != null) return;
    setPendingAction(action);
    setActionMessage(null);
    setActionError(null);
    setActionLink(null);
    try {
      const message = await request();
      setActionMessage(message);
      dispatchArticleDataChanged(article.id);
      router.refresh();
    } catch (error) {
      const raw = error instanceof Error ? error.message : "操作失败";
      setActionError(articleActionErrorMessage(raw));
    } finally {
      setPendingAction(null);
    }
  }

  return {
    actionMessage,
    actionError,
    actionLink,
    isFetchingContent: pendingAction === "fetchContent",
    isTranslating: pendingAction === "translate",
    isTogglingCandidate: pendingAction === "candidate",
    isProjecting: pendingAction === "project",
    isMarkingRead: pendingAction === "read",
    refreshFullContent: () =>
      run("fetchContent", async () => {
        if (article == null) return "";
        const created = await enqueueFetchContentJob(article.id);
        const job = await pollJobUntilTerminal(created.jobId);
        return contentFetchJobMessage(job);
      }),
    translateFullText: async () => {
      if (article == null || pendingAction != null) return null;
      setPendingAction("translate");
      setActionMessage(null);
      setActionError(null);
      setActionLink(null);
      try {
        const requested = await requestArticleTranslation(article.id);
        if (requested.contentZh != null) {
          setActionMessage("已切换到中文译文");
          return requested.contentZh;
        }
        if (requested.jobId == null) {
          setActionMessage("全文翻译请求已提交");
          return null;
        }
        const job = await pollJobUntilTerminal(requested.jobId, { intervalMs: 1000, maxAttempts: 60 });
        setActionMessage(translationJobMessage(job));
        dispatchArticleDataChanged(article.id);
        router.refresh();
        if (job.status !== "succeeded") return null;
        const refreshed = await getArticle(article.id);
        return refreshed.contentZh;
      } catch (error) {
        const raw = error instanceof Error ? error.message : "操作失败";
        setActionError(articleActionErrorMessage(raw));
        return null;
      } finally {
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
        setActionLink({ href: savedHref(article.id, currentLang), label: "查看候选" });
        return "已加入候选";
      }),
    markRead: () =>
      run("read", async () => {
        if (article == null) return "";
        await updateArticleState(article.id, { status: "read", readProgress: 1 });
        return "已标记为已读";
      }),
  };
}
