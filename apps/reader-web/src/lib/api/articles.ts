import { apiGet, apiPost } from "./client";
import type { components } from "./generated/schema";
import { sanitizeArticleHtml } from "@/lib/articles/service";
import type {
  Article,
  ArticleContentIssue,
  ArticleContentStatus,
  ArticleScore,
  ArticleStatus,
  DimensionReasons,
  DimensionKey,
  DimensionScores,
} from "@/lib/articles/types";
import { DIMENSION_KEYS } from "@/lib/articles/types";

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
  summary_zh?: string | null;
  state?: ApiArticleState | null;
};

export type ApiArticleDetail = ApiArticleItem & {
  content_html?: string | null;
  content_zh?: string | null;
  content_zh_status?: string | null;
  translated_at?: string | null;
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

export type ArticleTranslationResult = {
  status: string;
  contentZh: string | null;
  translatedAt: string | null;
  jobId: number | null;
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

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberRecord(value: unknown): DimensionScores {
  const result: Partial<Record<DimensionKey, number>> = {};
  const source = value != null && typeof value === "object" ? (value as Record<string, unknown>) : {};
  for (const key of DIMENSION_KEYS) {
    const raw = source[key];
    if (typeof raw === "number" && Number.isFinite(raw)) {
      result[key] = raw;
    }
  }
  return result as DimensionScores;
}

function stringRecord(value: unknown): DimensionReasons {
  const result: Partial<Record<DimensionKey, string>> = {};
  const source = value != null && typeof value === "object" ? (value as Record<string, unknown>) : {};
  for (const key of DIMENSION_KEYS) {
    const raw = source[key];
    if (typeof raw === "string") {
      result[key] = raw;
    }
  }
  return result as DimensionReasons;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function stringOr(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

// FastAPI emits the active score (or null) under `score`; see app/api/routes/articles.py score_public.
export function scoreFromApi(raw: unknown): ArticleScore | null {
  if (raw == null || typeof raw !== "object") return null;
  const s = raw as Record<string, unknown>;
  const overall = numberOrNull(s.overall);
  if (overall == null) return null;
  return {
    overall,
    tier: stringOr(s.tier, "skip"),
    dimensions: numberRecord(s.dimensions),
    tags: stringArray(s.tags),
    reason: stringOr(s.reason, ""),
    summaryZh: stringOr(s.summary_zh, ""),
    summaryOriginal: stringOr(s.summary_original, ""),
    sourceLanguage: stringOr(s.source_language, "unknown"),
    dimensionReasons: stringRecord(s.dimension_reasons),
    scoredAt: typeof s.scored_at === "string" ? s.scored_at : null,
  };
}

function articleBaseFromApi(item: ApiArticleItem, contentHtml: string): Article {
  const state = item.state ?? {};
  const saved = state.saved === true;
  const score = scoreFromApi(item.score);
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
    contentZh: null,
    contentZhStatus: null,
    translatedAt: null,
    contentStatus: contentStatusFromQuality(item.content_quality),
    contentIssue: contentIssueFromQuality(item.content_quality),
    contentFetchAttempted: item.content_quality != null && item.content_quality !== "snippet",
    summaryZh: score?.summaryZh || (item.summary_zh ?? ""),
    summaryOriginal: score?.summaryOriginal ?? "",
    sourceLanguage: score?.sourceLanguage ?? "unknown",
    status: articleStatusFromApi(state.status),
    starred: saved,
    publishedAt: item.published_at ?? null,
    score,
    readLater: saved,
    lastReadAt: state.status === "read" ? new Date().toISOString() : null,
  };
}

export function articleFromApiItem(item: ApiArticleItem): Article {
  return articleBaseFromApi(item, "");
}

export function articleFromApiDetail(detail: ApiArticleDetail): Article {
  const base = articleBaseFromApi(detail, sanitizeArticleHtml(detail.content_html ?? ""));
  return {
    ...base,
    contentZh: detail.content_zh ? sanitizeArticleHtml(detail.content_zh) : null,
    contentZhStatus: translationStatusFromApi(detail.content_zh_status),
    translatedAt: typeof detail.translated_at === "string" ? detail.translated_at : null,
    summaryOriginal: detail.summary_original ?? base.summaryOriginal,
    sourceLanguage: detail.source_language ?? base.sourceLanguage,
  };
}

function translationStatusFromApi(value: string | null | undefined): Article["contentZhStatus"] {
  if (value === "queued" || value === "running" || value === "succeeded" || value === "failed") {
    return value;
  }
  return null;
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

export async function requestArticleTranslation(articleId: number): Promise<ArticleTranslationResult> {
  const payload = await apiPost<{
    status: string;
    content_zh?: string | null;
    translated_at?: string | null;
    job_id?: number | null;
  }, undefined>(`/api/articles/${articleId}/translate`);
  return {
    status: payload.status,
    contentZh: payload.content_zh ? sanitizeArticleHtml(payload.content_zh) : null,
    translatedAt: payload.translated_at ?? null,
    jobId: payload.job_id ?? null,
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
