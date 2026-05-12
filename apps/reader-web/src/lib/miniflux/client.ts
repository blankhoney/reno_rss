import type { ArticleStatus } from "@/lib/articles/types";
import { getConfig } from "@/lib/config";

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

/**
 * Joins MINIFLUX base URL path prefix with a Miniflux API suffix (for example `"v1/feeds"`).
 * Preserves reverse-proxy base path behavior fixed in Task 5.
 */
export function buildMinifluxApiUrl(baseUrl: string, relativePath: string): URL {
  const cleanSuffix = relativePath.replace(/^\/+/, "");
  const url = new URL(baseUrl.replace(/\/$/, ""));
  const trimmedPath = url.pathname.replace(/\/+$/, "") || "";
  url.pathname = trimmedPath === "" ? `/${cleanSuffix}` : `${trimmedPath}/${cleanSuffix}`;
  return url;
}

export function buildEntriesUrl(baseUrl: string, filter: EntryFilter): URL {
  const url = buildMinifluxApiUrl(baseUrl, "v1/entries");

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
  return buildMinifluxApiUrl(baseUrl, `v1/entries/${entryId}`);
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

  private authJsonHeaders(): HeadersInit {
    return {
      Authorization: buildMinifluxBasicAuthorizationHeader(this.username, this.password),
      "Content-Type": "application/json",
    };
  }

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

  async updateEntries(entryIds: number[], status: "read" | "unread" | "removed"): Promise<void> {
    const response = await fetch(buildMinifluxApiUrl(this.baseUrl, "v1/entries").toString(), {
      method: "PUT",
      headers: this.authJsonHeaders(),
      body: JSON.stringify({ entry_ids: entryIds, status }),
      cache: "no-store",
      signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw new Error(`Miniflux update entries failed: ${response.status}`);
    }
  }

  /** Toggles starred state (Miniflux v2: `PUT /v1/entries/{id}/star`). */
  async toggleBookmark(entryId: number): Promise<void> {
    const response = await fetch(
      buildMinifluxApiUrl(this.baseUrl, `v1/entries/${entryId}/star`).toString(),
      {
        method: "PUT",
        headers: this.authJsonHeaders(),
        cache: "no-store",
        signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw new Error(`Miniflux toggle bookmark failed: ${response.status}`);
    }
  }

  /** Returns feeds as decoded JSON (typically an array of feed objects). */
  async getFeeds(): Promise<unknown> {
    const response = await fetch(buildMinifluxApiUrl(this.baseUrl, "v1/feeds").toString(), {
      headers: {
        Authorization: buildMinifluxBasicAuthorizationHeader(this.username, this.password),
      },
      cache: "no-store",
      signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw new Error(`Miniflux get feeds failed: ${response.status}`);
    }
    return response.json();
  }

  async createFeed(feedUrl: string, categoryId: number): Promise<number> {
    const response = await fetch(buildMinifluxApiUrl(this.baseUrl, "v1/feeds").toString(), {
      method: "POST",
      headers: this.authJsonHeaders(),
      body: JSON.stringify({ feed_url: feedUrl, category_id: categoryId }),
      cache: "no-store",
      signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw new Error(`Miniflux create feed failed: ${response.status}`);
    }
    const data = (await response.json()) as { feed_id?: number };
    if (typeof data.feed_id !== "number" || !Number.isFinite(data.feed_id)) {
      throw new Error("Miniflux create feed: missing feed_id");
    }
    return data.feed_id;
  }

  async deleteFeed(feedId: number): Promise<void> {
    const response = await fetch(buildMinifluxApiUrl(this.baseUrl, `v1/feeds/${feedId}`).toString(), {
      method: "DELETE",
      headers: this.authJsonHeaders(),
      cache: "no-store",
      signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
    });
    if (!response.ok) {
      throw new Error(`Miniflux delete feed failed: ${response.status}`);
    }
  }

  async refreshFeed(feedId: number): Promise<void> {
    const response = await fetch(
      buildMinifluxApiUrl(this.baseUrl, `v1/feeds/${feedId}/refresh`).toString(),
      {
        method: "PUT",
        headers: this.authJsonHeaders(),
        cache: "no-store",
        signal: AbortSignal.timeout(DEFAULT_MINIFLUX_FETCH_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      throw new Error(`Miniflux refresh feed failed: ${response.status}`);
    }
  }
}

export function getMinifluxClient(): MinifluxClient {
  const config = getConfig();
  return new MinifluxClient(config.MINIFLUX_API_BASE_URL, config.MINIFLUX_USERNAME, config.MINIFLUX_PASSWORD);
}
