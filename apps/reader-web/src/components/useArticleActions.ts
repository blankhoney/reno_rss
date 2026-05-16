"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Article } from "@/lib/articles/types";
import type { SummaryLangId } from "@/lib/articles/service";
import type { ArticleContentFetchResult } from "@/lib/articles/contentQuality";

type ActionKey = "score" | "fetchContent" | "candidate" | "project" | "read";

type ActionLink = {
  href: string;
  label: string;
};

type FetchContentResponse = {
  article?: Article;
  fetchResult?: ArticleContentFetchResult;
  error?: string;
};

function projectHref(entryId: number, lang: SummaryLangId): string {
  const qs = new URLSearchParams({
    module: "project",
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

function articleActionErrorMessage(error: string): string {
  if (error === "article_not_candidate") return "请先加入候选再立项";
  if (error === "manual_rescore_disabled") return "手动重评已关闭";
  if (error === "entry_not_found") return "文章不存在或不在当前 Miniflux 实例";
  if (error === "fetch_content_failed") return "全文抓取失败，请打开原文阅读";
  return error.trim() || "操作失败";
}

async function postArticleAction<TBody = unknown, TResponse = unknown>(
  entryId: number,
  path: string,
  body?: TBody,
): Promise<TResponse> {
  const response = await fetch(`/api/articles/${entryId}/${path}`, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = (await response.json().catch(() => null)) as
    | ({ error?: unknown } & TResponse)
    | null;

  if (!response.ok) {
    throw new Error(typeof data?.error === "string" ? data.error : "操作失败");
  }
  return (data ?? {}) as TResponse;
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
    isScoring: pendingAction === "score",
    isFetchingContent: pendingAction === "fetchContent",
    isTogglingCandidate: pendingAction === "candidate",
    isProjecting: pendingAction === "project",
    isMarkingRead: pendingAction === "read",
    scoreNow: () =>
      run("score", async () => {
        if (article == null) return "";
        await postArticleAction(article.id, "score", { force: true });
        return "评分已更新";
      }),
    refreshFullContent: () =>
      run("fetchContent", async () => {
        if (article == null) return "";
        try {
          const data = await postArticleAction<undefined, FetchContentResponse>(
            article.id,
            "fetch-content",
          );
          return data.fetchResult
            ? contentFetchResultMessage(data.fetchResult)
            : "全文刷新请求已完成";
        } catch (error) {
          const raw = error instanceof Error ? error.message : "fetch_content_failed";
          throw new Error(raw);
        }
      }),
    toggleCandidate: () =>
      run("candidate", async () => {
        if (article == null) return "";
        await postArticleAction(article.id, "star");
        return article.starred ? "已移出候选" : "已加入候选";
      }),
    enqueueProject: () =>
      run("project", async () => {
        if (article == null) return "";
        await postArticleAction(article.id, "project");
        setActionLink({ href: projectHref(article.id, currentLang), label: "查看已立项" });
        return "已立项";
      }),
    markRead: () =>
      run("read", async () => {
        if (article == null) return "";
        await postArticleAction(article.id, "read");
        return "已标记为已读";
      }),
  };
}
