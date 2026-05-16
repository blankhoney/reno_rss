import type { Article } from "@/lib/articles/types";
import type { FeedPreference } from "@/lib/scoring/repository";

export type FeedInfo = {
  id: number;
  title: string;
  feedUrl?: string;
  siteUrl?: string;
};

export type FeedQualitySummary = FeedInfo & {
  articleCount: number;
  fullCount: number;
  partialCount: number;
  blockedCount: number;
  fragmentCount: number;
  scoredCount: number;
  averageScore: number | null;
  highScoreCount: number;
  highScoreRate: number;
  starredCount: number;
  readLaterCount: number;
  projectCount: number;
  readCount: number;
  qualityScore: number;
  hidden: boolean;
  hiddenAt: string | null;
  reasons: string[];
};

type MutableFeedQuality = FeedInfo & {
  articleCount: number;
  fullCount: number;
  blockedCount: number;
  fragmentCount: number;
  scoreTotal: number;
  scoredCount: number;
  highScoreCount: number;
  starredCount: number;
  readLaterCount: number;
  projectCount: number;
  readCount: number;
};

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function emptyFeedQuality(feed: FeedInfo): MutableFeedQuality {
  return {
    ...feed,
    articleCount: 0,
    fullCount: 0,
    blockedCount: 0,
    fragmentCount: 0,
    scoreTotal: 0,
    scoredCount: 0,
    highScoreCount: 0,
    starredCount: 0,
    readLaterCount: 0,
    projectCount: 0,
    readCount: 0,
  };
}

function ensureFeed(
  map: Map<number, MutableFeedQuality>,
  feed: FeedInfo,
): MutableFeedQuality {
  const current = map.get(feed.id);
  if (current) {
    if (current.title.trim() === "" && feed.title.trim() !== "") current.title = feed.title;
    return current;
  }
  const next = emptyFeedQuality(feed);
  map.set(feed.id, next);
  return next;
}

function qualityReasons(summary: Omit<FeedQualitySummary, "reasons">): string[] {
  const reasons: string[] = [];
  const fullRate = summary.articleCount > 0 ? summary.fullCount / summary.articleCount : 0;
  const blockedRate = summary.articleCount > 0 ? summary.blockedCount / summary.articleCount : 0;
  const engagement =
    summary.starredCount + summary.readLaterCount + summary.projectCount + summary.readCount;

  if (summary.hidden) reasons.push("已手动隐藏");
  if (summary.articleCount === 0) reasons.push("最近样本为空");
  else if (fullRate >= 0.7) reasons.push("正文完整率高");
  else if (fullRate < 0.35) reasons.push("正文片段偏多");
  if (blockedRate >= 0.2) reasons.push("抓取常遇到错误页/登录墙");
  if ((summary.averageScore ?? 0) >= 70) reasons.push("平均评分较高");
  if (summary.scoredCount === 0 && summary.articleCount > 0) reasons.push("样本尚未评分");
  if (engagement > 0) reasons.push("有阅读/候选/稍后读行为");
  return reasons.slice(0, 4);
}

function finalizeFeedQuality(
  feed: MutableFeedQuality,
  preference: FeedPreference | undefined,
): FeedQualitySummary {
  const articleCount = feed.articleCount;
  const partialCount = Math.max(0, articleCount - feed.fullCount);
  const fullRate = articleCount > 0 ? feed.fullCount / articleCount : 0;
  const blockedRate = articleCount > 0 ? feed.blockedCount / articleCount : 0;
  const fragmentRate = articleCount > 0 ? feed.fragmentCount / articleCount : 0;
  const averageScore = feed.scoredCount > 0 ? Math.round(feed.scoreTotal / feed.scoredCount) : null;
  const highScoreRate = feed.scoredCount > 0 ? feed.highScoreCount / feed.scoredCount : 0;
  const engagement =
    feed.starredCount + feed.readLaterCount + feed.projectCount + feed.readCount;
  const scoreComponent = averageScore == null ? 0.35 : averageScore / 100;
  const engagementComponent = Math.min(1, engagement / 5);
  const qualityScore = clampScore(
    45 * fullRate +
      30 * scoreComponent +
      15 * highScoreRate +
      10 * engagementComponent -
      25 * blockedRate -
      8 * fragmentRate,
  );
  const base = {
    id: feed.id,
    title: feed.title,
    feedUrl: feed.feedUrl,
    siteUrl: feed.siteUrl,
    articleCount,
    fullCount: feed.fullCount,
    partialCount,
    blockedCount: feed.blockedCount,
    fragmentCount: feed.fragmentCount,
    scoredCount: feed.scoredCount,
    averageScore,
    highScoreCount: feed.highScoreCount,
    highScoreRate,
    starredCount: feed.starredCount,
    readLaterCount: feed.readLaterCount,
    projectCount: feed.projectCount,
    readCount: feed.readCount,
    qualityScore,
    hidden: preference?.hidden ?? false,
    hiddenAt: preference?.hiddenAt ?? null,
  };
  return { ...base, reasons: qualityReasons(base) };
}

export function buildFeedQualitySummaries(input: {
  feeds: FeedInfo[];
  articles: Article[];
  preferences: Map<number, FeedPreference>;
  projectEntryIds?: Set<number>;
}): FeedQualitySummary[] {
  const map = new Map<number, MutableFeedQuality>();
  for (const feed of input.feeds) {
    ensureFeed(map, feed);
  }

  for (const article of input.articles) {
    if (article.feedId == null) continue;
    const feed = ensureFeed(map, {
      id: article.feedId,
      title: article.feedTitle || `Feed ${article.feedId}`,
    });
    feed.articleCount += 1;
    if (article.contentStatus === "full") feed.fullCount += 1;
    if (article.contentIssue === "blocked_or_error_page") feed.blockedCount += 1;
    if (article.contentIssue === "rss_fragment") feed.fragmentCount += 1;
    if (article.score != null) {
      feed.scoredCount += 1;
      feed.scoreTotal += article.score.overall;
      if (article.score.overall >= 70) feed.highScoreCount += 1;
    }
    if (article.starred) feed.starredCount += 1;
    if (article.readLater) feed.readLaterCount += 1;
    if (article.lastReadAt) feed.readCount += 1;
    if (input.projectEntryIds?.has(article.id)) feed.projectCount += 1;
  }

  return [...map.values()]
    .map((feed) => finalizeFeedQuality(feed, input.preferences.get(feed.id)))
    .sort((a, b) => {
      if (a.hidden !== b.hidden) return a.hidden ? 1 : -1;
      const qualityDelta = b.qualityScore - a.qualityScore;
      if (qualityDelta !== 0) return qualityDelta;
      const countDelta = b.articleCount - a.articleCount;
      if (countDelta !== 0) return countDelta;
      return a.title.localeCompare(b.title);
    });
}

export function feedQualityMap(summaries: FeedQualitySummary[]): Map<number, FeedQualitySummary> {
  return new Map(summaries.map((summary) => [summary.id, summary]));
}
