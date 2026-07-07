import { apiGet, apiPost, apiPut, type ApiRequestInit } from "./client";
import type { components } from "./generated/schema";
import { sanitizeArticleHtml } from "@/lib/articles/service";
import type {
  Article,
  ArticleFeedback,
  ArticleFeedbackType,
  ArticleContentIssue,
  ArticleContentStatus,
  ArticleScore,
  ArticleStatus,
  DimensionReasons,
  DimensionKey,
  DimensionScores,
} from "@/lib/articles/types";
import { ARTICLE_FEEDBACK_TYPES, DIMENSION_KEYS } from "@/lib/articles/types";

type ApiArticleState = {
  status?: string | null;
  saved?: boolean | null;
  project?: boolean | null;
  read_progress?: number | null;
};

type ApiArticleFeedback = {
  user_score?: number | null;
  feedback_type?: string | null;
  reason?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
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
  my_feedback?: ApiArticleFeedback | null;
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

export type ArticleStats = {
  total: number;
  scored: number;
  unscored: number;
};

export type ArticleStatePatch = {
  status?: "read" | "unread" | "skipped";
  saved?: boolean;
  project?: boolean;
  readProgress?: number;
};

export type ArticleFeedbackPatch = {
  userScore: number;
  feedbackType: ArticleFeedbackType;
  reason?: string;
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
  maxIntervalMs?: number;
  maxAttempts?: number;
  backoffFactor?: number;
  jitterRatio?: number;
  signal?: AbortSignal;
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

function feedbackTypeFromApi(value: string | null | undefined): ArticleFeedbackType {
  return ARTICLE_FEEDBACK_TYPES.includes(value as ArticleFeedbackType)
    ? (value as ArticleFeedbackType)
    : "other";
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

export function feedbackFromApi(raw: ApiArticleFeedback | null | undefined): ArticleFeedback | null {
  if (raw == null) return null;
  if (typeof raw.user_score !== "number" || !Number.isFinite(raw.user_score)) return null;
  return {
    userScore: raw.user_score,
    feedbackType: feedbackTypeFromApi(raw.feedback_type),
    reason: raw.reason ?? "",
    createdAt: typeof raw.created_at === "string" ? raw.created_at : null,
    updatedAt: typeof raw.updated_at === "string" ? raw.updated_at : null,
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
    project: state.project === true,
    publishedAt: item.published_at ?? null,
    score,
    myFeedback: feedbackFromApi(item.my_feedback),
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

export async function getArticleStats(): Promise<ArticleStats> {
  const payload = await apiGet<{ total?: number; scored?: number; unscored?: number }>(
    "/api/articles/stats",
  );
  return {
    total: payload.total ?? 0,
    scored: payload.scored ?? 0,
    unscored: payload.unscored ?? 0,
  };
}

export async function getArticle(articleId: number): Promise<Article> {
  return articleFromApiDetail(await apiGet<ApiArticleDetail>(`/api/articles/${articleId}`));
}

export async function updateArticleState(articleId: number, patch: ArticleStatePatch): Promise<void> {
  const body: components["schemas"]["ArticleStateRequest"] = {
    status: patch.status,
    saved: patch.saved,
    project: patch.project,
    read_progress: patch.readProgress,
  };
  await apiPost(`/api/articles/${articleId}/state`, body);
}

export async function saveArticleFeedback(
  articleId: number,
  patch: ArticleFeedbackPatch,
): Promise<ArticleFeedback> {
  const payload = await apiPut<
    { feedback?: ApiArticleFeedback },
    {
      user_score: number;
      feedback_type: string;
      reason: string;
    }
  >(`/api/articles/${articleId}/feedback`, {
    user_score: patch.userScore,
    feedback_type: patch.feedbackType,
    reason: patch.reason ?? "",
  });
  const feedback = feedbackFromApi(payload.feedback);
  if (feedback === null) {
    throw new Error("API returned invalid article feedback");
  }
  return feedback;
}

export async function enqueueFetchContentJob(
  articleId: number,
  init?: ApiRequestInit,
): Promise<EnqueuedJob> {
  const payload = await apiPost<{ job_id: number; status: string }, undefined>(
    `/api/articles/${articleId}/fetch-content`,
    undefined,
    init,
  );
  return {
    jobId: payload.job_id,
    status: payload.status,
  };
}

export async function requestArticleTranslation(
  articleId: number,
  init?: ApiRequestInit,
): Promise<ArticleTranslationResult> {
  const payload = await apiPost<{
    status: string;
    content_zh?: string | null;
    translated_at?: string | null;
    job_id?: number | null;
  }, undefined>(`/api/articles/${articleId}/translate`, undefined, init);
  return {
    status: payload.status,
    contentZh: payload.content_zh ? sanitizeArticleHtml(payload.content_zh) : null,
    translatedAt: payload.translated_at ?? null,
    jobId: payload.job_id ?? null,
  };
}

export async function getJob(jobId: number, init?: ApiRequestInit): Promise<ApiJob> {
  const payload = await apiGet<ApiJobResponse>(`/api/jobs/${jobId}`, init);
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
  {
    intervalMs = 1000,
    maxIntervalMs = 5000,
    maxAttempts = 30,
    backoffFactor = 1.6,
    jitterRatio = 0.2,
    signal,
  }: PollOptions = {},
): Promise<ApiJob> {
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    throwIfAborted(signal);
    const job = await getJob(jobId, { signal });
    if (terminalJobStatus(job.status)) return job;
    if (attempt < maxAttempts - 1) {
      await sleep(pollDelayMs(attempt, intervalMs, maxIntervalMs, backoffFactor, jitterRatio), signal);
    }
  }
  throwIfAborted(signal);
  return getJob(jobId, { signal });
}

function pollDelayMs(
  attempt: number,
  intervalMs: number,
  maxIntervalMs: number,
  backoffFactor: number,
  jitterRatio: number,
): number {
  if (intervalMs <= 0 || maxIntervalMs <= 0) return 0;
  const base = Math.min(intervalMs * Math.max(1, backoffFactor) ** attempt, maxIntervalMs);
  const jitter = base * Math.max(0, jitterRatio) * Math.random();
  return Math.round(base + jitter);
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  throwIfAborted(signal);
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeoutId = globalThis.setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, ms);

    function abort() {
      globalThis.clearTimeout(timeoutId);
      reject(abortError(signal));
    }

    signal?.addEventListener("abort", abort, { once: true });
  });
}

function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw abortError(signal);
  }
}

function abortError(signal?: AbortSignal): Error {
  if (signal?.reason instanceof Error) return signal.reason;
  return new DOMException("The operation was aborted.", "AbortError");
}
