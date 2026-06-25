import { apiGet, apiPost } from "./client";
import type { components } from "./generated/schema";
import { sanitizeArticleHtml } from "@/lib/articles/service";
import type { Article, ArticleContentIssue, ArticleContentStatus, ArticleStatus } from "@/lib/articles/types";

type ApiArticleState = {
  status?: string | null;
  saved?: boolean | null;
  read_progress?: number | null;
};

type ApiArticleFeed = {
  id?: number | null;
  title?: string | null;
} | null;

type ApiArticleCategory = {
  id?: number | null;
  title?: string | null;
} | null;

export type ApiArticleItem = {
  id: number;
  title: string;
  url: string;
  feed?: ApiArticleFeed;
  category?: ApiArticleCategory;
  published_at?: string | null;
  content_quality?: string | null;
  score?: unknown;
  state?: ApiArticleState | null;
};

export type ApiArticleDetail = ApiArticleItem & {
  content_html?: string | null;
  content_text?: string | null;
  content_source?: string | null;
  summary_original?: string | null;
  source_language?: string | null;
  sources?: unknown[];
};

export type ArticleListPage = {
  articles: Article[];
  nextCursor: string | null;
  hasMore: boolean;
};

export type ArticleStatePatch = {
  status?: "read" | "unread" | "skipped";
  saved?: boolean;
  readProgress?: number;
};

export type EnqueuedJob = {
  jobId: number;
  status: string;
};

export type ApiJob = {
  id: number;
  jobType: string;
  status: string;
  progress: unknown;
  result: unknown;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
};

type ApiListResponse = {
  items?: ApiArticleItem[];
  next_cursor?: string | null;
  has_more?: boolean;
};

type ApiJobResponse = {
  id: number;
  job_type: string;
  status: string;
  progress: unknown;
  result: unknown;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

type PollOptions = {
  intervalMs?: number;
  maxAttempts?: number;
};

function contentStatusFromQuality(quality: string | null | undefined): ArticleContentStatus {
  return quality === "full" ? "full" : "partial";
}

function contentIssueFromQuality(quality: string | null | undefined): ArticleContentIssue {
  if (quality === "full") return null;
  if (quality === "blocked_or_error_page") return "blocked_or_error_page";
  if (quality === "fetch_failed") return "fetch_failed";
  return "rss_fragment";
}

function articleStatusFromApi(status: string | null | undefined): ArticleStatus {
  if (status === "read" || status === "skipped") return status;
  return "unread";
}

function feedTitle(feed: ApiArticleFeed): string {
  return feed?.title?.trim() || (feed?.id != null ? `Feed #${feed.id}` : "未知来源");
}

function articleBaseFromApi(item: ApiArticleItem, contentHtml: string): Article {
  const state = item.state ?? {};
  const saved = state.saved === true;
  return {
    id: item.id,
    userId: 0,
    feedId: item.feed?.id ?? null,
    feedTitle: feedTitle(item.feed ?? null),
    categoryId: item.category?.id ?? null,
    categoryTitle: item.category?.title ?? "",
    title: item.title,
    url: item.url,
    contentHtml,
    contentStatus: contentStatusFromQuality(item.content_quality),
    contentIssue: contentIssueFromQuality(item.content_quality),
    contentFetchAttempted: item.content_quality != null && item.content_quality !== "snippet",
    summaryZh: "",
    summaryOriginal: "",
    sourceLanguage: "unknown",
    status: articleStatusFromApi(state.status),
    starred: saved,
    publishedAt: item.published_at ?? null,
    score: null,
    readLater: saved,
    lastReadAt: state.status === "read" ? new Date().toISOString() : null,
  };
}

export function articleFromApiItem(item: ApiArticleItem): Article {
  return articleBaseFromApi(item, "");
}

export function articleFromApiDetail(detail: ApiArticleDetail): Article {
  return {
    ...articleBaseFromApi(detail, sanitizeArticleHtml(detail.content_html ?? "")),
    summaryOriginal: detail.summary_original ?? "",
    sourceLanguage: detail.source_language ?? "unknown",
  };
}

export async function listArticles({
  limit,
  cursor,
}: {
  limit: number;
  cursor?: string | null;
}): Promise<ArticleListPage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  const payload = await apiGet<ApiListResponse>(`/api/articles?${params.toString()}`);
  return {
    articles: (payload.items ?? []).map(articleFromApiItem),
    nextCursor: payload.next_cursor ?? null,
    hasMore: payload.has_more === true,
  };
}

export async function getArticle(articleId: number): Promise<Article> {
  return articleFromApiDetail(await apiGet<ApiArticleDetail>(`/api/articles/${articleId}`));
}

export async function updateArticleState(articleId: number, patch: ArticleStatePatch): Promise<void> {
  const body: components["schemas"]["ArticleStateRequest"] = {
    status: patch.status,
    saved: patch.saved,
    read_progress: patch.readProgress,
  };
  await apiPost(`/api/articles/${articleId}/state`, body);
}

export async function enqueueFetchContentJob(articleId: number): Promise<EnqueuedJob> {
  const payload = await apiPost<{ job_id: number; status: string }, undefined>(
    `/api/articles/${articleId}/fetch-content`,
  );
  return {
    jobId: payload.job_id,
    status: payload.status,
  };
}

export async function getJob(jobId: number): Promise<ApiJob> {
  const payload = await apiGet<ApiJobResponse>(`/api/jobs/${jobId}`);
  return {
    id: payload.id,
    jobType: payload.job_type,
    status: payload.status,
    progress: payload.progress,
    result: payload.result,
    lastError: payload.last_error,
    createdAt: payload.created_at,
    updatedAt: payload.updated_at,
    completedAt: payload.completed_at,
  };
}

export function terminalJobStatus(status: string): boolean {
  return status === "succeeded" || status === "failed";
}

export async function pollJobUntilTerminal(
  jobId: number,
  { intervalMs = 1000, maxAttempts = 30 }: PollOptions = {},
): Promise<ApiJob> {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const job = await getJob(jobId);
    if (terminalJobStatus(job.status)) return job;
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => globalThis.setTimeout(resolve, intervalMs));
    }
  }
  return getJob(jobId);
}
