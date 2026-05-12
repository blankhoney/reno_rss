import type { ArticleStatus } from "@/lib/articles/types";

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

export function buildEntriesUrl(baseUrl: string, filter: EntryFilter): URL {
  const url = new URL("/v1/entries", baseUrl.replace(/\/$/, ""));
  if (filter.status && filter.status !== "all") url.searchParams.set("status", filter.status);
  if (filter.starred !== undefined) url.searchParams.set("starred", String(filter.starred));
  if (filter.categoryId !== undefined) url.searchParams.set("category_id", String(filter.categoryId));
  url.searchParams.set("limit", String(filter.limit ?? 50));
  url.searchParams.set("offset", String(filter.offset ?? 0));
  url.searchParams.set("order", "published_at");
  url.searchParams.set("direction", "desc");
  return url;
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
        Authorization: `Basic ${Buffer.from(`${this.username}:${this.password}`).toString("base64")}`,
      },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`Miniflux entries request failed: ${response.status}`);
    }
    const data = (await response.json()) as { entries?: MinifluxEntry[] };
    return (data.entries ?? []).map(normalizeMinifluxEntry);
  }
}
