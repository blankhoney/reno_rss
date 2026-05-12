import type { ArticleStatus } from "@/lib/articles/types";

/**
 * This module is intended for the Node.js server runtime only: HTTP Basic credentials
 * are encoded with Buffer. Do not bundle or import into Edge Middleware / Edge routes.
 *
 * Consumers can assert `MINIFLUX_HTTP_CLIENT_RUNTIME === "nodejs"` when wiring server code.
 */
export const MINIFLUX_HTTP_CLIENT_RUNTIME = "nodejs" as const;

export const DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS = 10_000;

export const DEFAULT_ARTICLES_LIST_LIMIT = 50;
export const MIN_ARTICLES_LIST_LIMIT = 1;
export const MAX_ARTICLES_LIST_LIMIT = 100;

type EntryFilter = {
  status?: ArticleStatus | "all";
  limit?: number;
  offset?: number;
  categoryId?: number;
  starred?: boolean;
};

export type MinifluxEntry = {
  id: number;
  user_id: number;
  feed_id?: number;
  title?: string;
  url?: string;
  content?: string;
  status?: ArticleStatus;
  starred?: boolean;
  published_at?: string;
  feed?: {
    id?: number;
    title?: string;
    category?: {
      id?: number;
      title?: string;
    };
  };
};

/**
 * Builds the `Authorization` header value for HTTP Basic authentication (requires Node Buffer).
 */
export function buildMinifluxBasicAuthorizationHeader(username: string, password: string): string {
  return `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
}

export function buildEntriesUrl(baseUrl: string, filter: EntryFilter): URL {
  const url = new URL(baseUrl.replace(/\/$/, ""));
  const trimmedPath = url.pathname.replace(/\/+$/, "") || "";
  url.pathname = trimmedPath === "" ? "/v1/entries" : `${trimmedPath}/v1/entries`;

  if (filter.status && filter.status !== "all") url.searchParams.set("status", filter.status);
  if (filter.starred !== undefined) url.searchParams.set("starred", String(filter.starred));
  if (filter.categoryId !== undefined) url.searchParams.set("category_id", String(filter.categoryId));
  url.searchParams.set("limit", String(filter.limit ?? 50));
  url.searchParams.set("offset", String(filter.offset ?? 0));
  url.searchParams.set("order", "published_at");
  url.searchParams.set("direction", "desc");
  return url;
}

export function buildEntryUrl(baseUrl: string, entryId: number): URL {
  const url = new URL(baseUrl.replace(/\/$/, ""));
  const trimmedPath = url.pathname.replace(/\/+$/, "") || "";
  url.pathname =
    trimmedPath === "" ? `/v1/entries/${entryId}` : `${trimmedPath}/v1/entries/${entryId}`;
  return url;
}

/**
 * Parses the articles list `limit` query param: default 50, non-integers fall back to default,
 * integers are clamped to {@link MIN_ARTICLES_LIST_LIMIT}..{@link MAX_ARTICLES_LIST_LIMIT}.
 */
export function parseArticlesListLimitParam(value: string | null): number {
  if (value === null || value === "") {
    return DEFAULT_ARTICLES_LIST_LIMIT;
  }
  const n = Number(value);
  if (!Number.isInteger(n)) {
    return DEFAULT_ARTICLES_LIST_LIMIT;
  }
  return Math.min(MAX_ARTICLES_LIST_LIMIT, Math.max(MIN_ARTICLES_LIST_LIMIT, n));
}

export function normalizeMinifluxEntry(entry: MinifluxEntry) {
  return {
    id: entry.id,
    userId: entry.user_id,
    feedId: entry.feed_id ?? entry.feed?.id ?? null,
    feedTitle: entry.feed?.title ?? "",
    categoryId: entry.feed?.category?.id ?? null,
    categoryTitle: entry.feed?.category?.title ?? "未分类",
    title: entry.title ?? "",
    url: entry.url ?? "",
    contentHtml: entry.content ?? "",
    status: entry.status ?? "unread",
    starred: Boolean(entry.starred),
    publishedAt: entry.published_at ?? null,
  };
}

export class MinifluxClient {
  constructor(
    private readonly baseUrl: string,
    private readonly username: string,
    private readonly password: string,
  ) {}

  async getEntries(filter: EntryFilter): Promise<ReturnType<typeof normalizeMinifluxEntry>[]> {
    const response = await fetch(buildEntriesUrl(this.baseUrl, filter), {
      headers: {
        Authorization: buildMinifluxBasicAuthorizationHeader(this.username, this.password),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw new Error(`Miniflux entries request failed: ${response.status}`);
    }
    const data = (await response.json()) as { entries?: MinifluxEntry[] };
    return (data.entries ?? []).map(normalizeMinifluxEntry);
  }

  /**
   * Fetches a single entry by id. Returns `null` when Miniflux responds with 404.
   */
  async getEntry(entryId: number): Promise<ReturnType<typeof normalizeMinifluxEntry> | null> {
    const response = await fetch(buildEntryUrl(this.baseUrl, entryId).toString(), {
      headers: {
        Authorization: buildMinifluxBasicAuthorizationHeader(this.username, this.password),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
    });
    if (response.status === 404) {
      return null;
    }
    if (!response.ok) {
      throw new Error(`Miniflux entry request failed: ${response.status}`);
    }
    const data = (await response.json()) as MinifluxEntry;
    return normalizeMinifluxEntry(data);
  }
}
