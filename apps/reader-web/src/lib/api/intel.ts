import { apiGet, apiPost, apiPut } from "./client";

export type ClusterItem = {
  id: string;
  label: string;
  mainArticleId: number;
  relatedArticleIds: number[];
  size: number;
};

export type ThemeItem = {
  label: string;
  weight: number;
  articleIds: number[];
};

export type FeedItem = {
  id: number;
  title: string;
  status: string;
  hidden: boolean;
  userPriority: number;
  articleCount: number;
};

export type RuleItem = {
  type: string;
  feedId?: number | null;
  keyword?: string | null;
  weight?: number | null;
};

export type SavedSearchItem = {
  id?: number;
  name: string;
  q: string;
  module: string;
  sort: string;
};

export type InterestProfile = {
  generatedAt: string | null;
  keywords: Array<{ term: string; weight: number }>;
  feedbackCounts: Record<string, number>;
  projectCount: number;
  annotationCount: number;
  resetAt: string | null;
};

export type AnnotationSearchItem = {
  id: number;
  articleId: number;
  content: string;
  selectedText: string | null;
  articleTitle: string | null;
};

export function researchCitationHref(articleId: number, quote?: string): string {
  const params = new URLSearchParams({
    module: "research",
    sort: "default",
    lang: "zh",
  });
  if (quote?.trim()) params.set("quote", quote.trim());
  return `/read/${articleId}?${params.toString()}`;
}

export function savedSearchHref(item: SavedSearchItem): string {
  const params = new URLSearchParams({
    module: "search",
    filter: item.module || "all",
    sort: item.sort || "latest",
    lang: "zh",
  });
  if (item.q.trim()) params.set("q", item.q.trim());
  return `/?${params.toString()}`;
}

export async function listClusters(limit = 12): Promise<ClusterItem[]> {
  const payload = await apiGet<{
    clusters?: Array<{
      id?: string;
      label?: string;
      main_article_id?: number;
      related_article_ids?: number[];
      size?: number;
    }>;
  }>(`/api/clusters/latest?limit=${limit}`);
  const items: ClusterItem[] = [];
  for (const item of payload.clusters ?? []) {
    if (item.main_article_id == null) continue;
    items.push({
      id: String(item.id ?? item.main_article_id),
      label: item.label ?? `Cluster #${item.main_article_id}`,
      mainArticleId: item.main_article_id,
      relatedArticleIds: item.related_article_ids ?? [],
      size: item.size ?? 1,
    });
  }
  return items;
}

export async function listThemes(maxThemes = 20): Promise<ThemeItem[]> {
  const payload = await apiGet<{
    themes?: Array<{
      label?: string;
      weight?: number;
      article_ids?: number[];
    }>;
  }>(`/api/themes/latest?max_themes=${maxThemes}`);
  const items: ThemeItem[] = [];
  for (const item of payload.themes ?? []) {
    if (!item.label) continue;
    items.push({
      label: item.label,
      weight: typeof item.weight === "number" ? item.weight : 0,
      articleIds: item.article_ids ?? [],
    });
  }
  return items;
}

export async function listFeeds(): Promise<FeedItem[]> {
  const payload = await apiGet<{
    items?: Array<{
      id?: number;
      title?: string;
      status?: string;
      hidden?: boolean;
      user_priority?: number;
      article_count?: number;
    }>;
  }>("/api/feeds");
  const items: FeedItem[] = [];
  for (const item of payload.items ?? []) {
    if (item.id == null) continue;
    items.push({
      id: item.id,
      title: item.title ?? `Feed #${item.id}`,
      status: item.status ?? "unknown",
      hidden: item.hidden === true,
      userPriority: typeof item.user_priority === "number" ? item.user_priority : 0,
      articleCount: typeof item.article_count === "number" ? item.article_count : 0,
    });
  }
  return items;
}

export async function listRules(): Promise<RuleItem[]> {
  const payload = await apiGet<{
    rules?: Array<{
      type?: string;
      feed_id?: number | null;
      keyword?: string | null;
      weight?: number | null;
    }>;
  }>("/api/rules");
  const rules: RuleItem[] = [];
  for (const item of payload.rules ?? []) {
    if (!item.type) continue;
    rules.push({
      type: item.type,
      feedId: item.feed_id ?? null,
      keyword: item.keyword ?? null,
      weight: item.weight ?? null,
    });
  }
  return rules;
}

export async function putRules(rules: RuleItem[]): Promise<RuleItem[]> {
  const payload = await apiPut<
    { rules?: Array<Record<string, unknown>> },
    {
      rules: Array<{
        type: string;
        feed_id?: number | null;
        keyword?: string | null;
        weight?: number | null;
      }>;
    }
  >("/api/rules", {
    rules: rules.map((rule) => ({
      type: rule.type,
      feed_id: rule.feedId ?? null,
      keyword: rule.keyword ?? null,
      weight: rule.weight ?? null,
    })),
  });
  return (payload.rules ?? []).map((item) => ({
    type: String(item.type ?? ""),
    feedId: (item.feed_id as number | null | undefined) ?? null,
    keyword: (item.keyword as string | null | undefined) ?? null,
    weight: (item.weight as number | null | undefined) ?? null,
  }));
}

export async function listSavedSearches(): Promise<SavedSearchItem[]> {
  const payload = await apiGet<{
    items?: Array<{
      id?: number;
      name?: string;
      q?: string;
      module?: string;
      sort?: string;
    }>;
  }>("/api/saved-searches");
  const items: SavedSearchItem[] = [];
  for (const item of payload.items ?? []) {
    if (!item.name) continue;
    items.push({
      id: item.id,
      name: item.name,
      q: item.q ?? "",
      module: item.module ?? "all",
      sort: item.sort ?? "latest",
    });
  }
  return items;
}

export async function putSavedSearches(items: SavedSearchItem[]): Promise<SavedSearchItem[]> {
  const payload = await apiPut<
    { items?: Array<Record<string, unknown>> },
    { items: Array<{ name: string; q: string; module: string; sort: string }> }
  >("/api/saved-searches", {
    items: items.map((item) => ({
      name: item.name,
      q: item.q,
      module: item.module,
      sort: item.sort,
    })),
  });
  return (payload.items ?? []).map((item) => ({
    id: item.id as number | undefined,
    name: String(item.name ?? ""),
    q: String(item.q ?? ""),
    module: String(item.module ?? "all"),
    sort: String(item.sort ?? "latest"),
  }));
}

export async function enqueueResearchJob(input: {
  scope: "topn" | "project" | "topic";
  question: string;
  topic?: string;
  maxArticles?: number;
}): Promise<{ jobId: number; pollUrl: string }> {
  const payload = await apiPost<
    { job_id?: number; poll_url?: string },
    {
      scope: string;
      question: string;
      topic?: string;
      max_articles?: number;
    }
  >("/api/research/jobs", {
    scope: input.scope,
    question: input.question,
    topic: input.topic,
    max_articles: input.maxArticles ?? 10,
  });
  if (payload.job_id == null) {
    throw new Error("Research job missing job_id");
  }
  return {
    jobId: payload.job_id,
    pollUrl: payload.poll_url ?? `/api/jobs/${payload.job_id}`,
  };
}

export async function getInterestProfile(): Promise<InterestProfile> {
  const payload = await apiGet<{
    generated_at?: string | null;
    keywords?: Array<{ term?: string; weight?: number }>;
    feedback_counts?: Record<string, number>;
    project_count?: number;
    annotation_count?: number;
    reset_at?: string | null;
  }>("/api/me/interest");
  const keywords: Array<{ term: string; weight: number }> = [];
  for (const item of payload.keywords ?? []) {
    if (!item.term) continue;
    keywords.push({
      term: item.term,
      weight: typeof item.weight === "number" ? item.weight : 0,
    });
  }
  return {
    generatedAt: payload.generated_at ?? null,
    keywords,
    feedbackCounts: payload.feedback_counts ?? {},
    projectCount: payload.project_count ?? 0,
    annotationCount: payload.annotation_count ?? 0,
    resetAt: payload.reset_at ?? null,
  };
}

export async function resetInterestProfile(): Promise<InterestProfile> {
  await apiPost("/api/me/interest/reset", {});
  return getInterestProfile();
}

export async function exportInterestProfile(): Promise<InterestProfile> {
  return getInterestProfile();
}

export async function searchAnnotations(
  q: string,
  limit = 30,
): Promise<AnnotationSearchItem[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  const payload = await apiGet<{
    items?: Array<{
      id?: number;
      article_id?: number;
      content?: string;
      selected_text?: string | null;
      article_title?: string | null;
    }>;
  }>(`/api/annotations/search?${params.toString()}`);
  const items: AnnotationSearchItem[] = [];
  for (const item of payload.items ?? []) {
    if (item.id == null || item.article_id == null || typeof item.content !== "string") {
      continue;
    }
    items.push({
      id: item.id,
      articleId: item.article_id,
      content: item.content,
      selectedText: item.selected_text ?? null,
      articleTitle: item.article_title ?? null,
    });
  }
  return items;
}
