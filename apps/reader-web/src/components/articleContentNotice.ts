import type { Article } from "@/lib/articles/types";

export function articleContentNotice(article: Article): string | null {
  if (article.contentStatus !== "partial") return null;
  if (article.contentIssue === "blocked_or_error_page") {
    return "源站只返回错误页或登录墙，当前仍显示 RSS 片段。可打开原文阅读；问答将基于片段和评分信息回答，可能不完整。";
  }
  if (article.contentIssue === "fetch_failed") {
    return "系统尝试抓取全文失败，当前仍显示 RSS 片段。可打开原文阅读；问答将基于片段和评分信息回答，可能不完整。";
  }
  if (article.contentFetchAttempted) {
    return "系统已尝试使用 Miniflux 抓取全文，但当前仍只有 RSS 片段。可打开原文阅读；问答将基于片段和评分信息回答，可能不完整。";
  }
  return "当前仅有 RSS 片段，可能不是完整正文。可尝试刷新全文，或打开原文阅读；问答将基于片段和评分信息回答，可能不完整。";
}

export function articleAgentNotice(article: Article): string | null {
  if (article.contentStatus !== "partial") return null;
  if (article.contentIssue === "blocked_or_error_page") {
    return "源站返回错误页或登录墙，回答只基于当前片段和评分信息，可能不完整。";
  }
  return "正文不完整，回答将基于当前片段和评分信息，可能不完整。";
}
