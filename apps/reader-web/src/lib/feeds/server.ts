import { getConfig } from "@/lib/config";
import { getMinifluxClient } from "@/lib/miniflux/client";
import { mergeArticleData } from "@/lib/articles/service";
import { getPool } from "@/lib/scoring/db";
import {
  getFeedPreferences,
  getProjectEntryIds,
  getReaderStatesByEntryIds,
  getScoresByEntryIds,
} from "@/lib/scoring/repository";
import {
  buildFeedQualitySummaries,
  feedQualityMap,
  type FeedInfo,
  type FeedQualitySummary,
} from "./quality";

const FEED_QUALITY_SAMPLE_LIMIT = 300;

export async function getFeedQualitySample() {
  const config = getConfig();
  const miniflux = getMinifluxClient();
  const [feeds, baseArticles] = await Promise.all([
    miniflux.getFeeds(),
    miniflux.getEntries({ status: "all", limit: FEED_QUALITY_SAMPLE_LIMIT }),
  ]);
  const entryIds = baseArticles.map((article) => article.id);
  const feedIds = [
    ...new Set([
      ...feeds.map((feed) => feed.id),
      ...baseArticles.flatMap((article) => (article.feedId == null ? [] : [article.feedId])),
    ]),
  ];
  const pool = getPool();
  const [scores, states, preferences, projectIds] = await Promise.all([
    getScoresByEntryIds(pool, config.READER_TENANT_ID, entryIds),
    getReaderStatesByEntryIds(
      pool,
      config.READER_TENANT_ID,
      config.READER_MINIFLUX_USER_ID,
      entryIds,
    ),
    getFeedPreferences(pool, config.READER_TENANT_ID, feedIds),
    getProjectEntryIds(pool, config.READER_TENANT_ID, FEED_QUALITY_SAMPLE_LIMIT),
  ]);
  const articles = mergeArticleData(baseArticles, scores, states);
  const feedInfos: FeedInfo[] = feeds.map((feed) => ({
    id: feed.id,
    title: feed.title,
    feedUrl: feed.feed_url,
    siteUrl: feed.site_url,
  }));
  const summaries = buildFeedQualitySummaries({
    feeds: feedInfos,
    articles,
    preferences,
    projectEntryIds: new Set(projectIds),
  });

  return { articles, summaries, preferences, qualityByFeed: feedQualityMap(summaries) };
}

export async function listFeedQualitySummaries(): Promise<FeedQualitySummary[]> {
  return (await getFeedQualitySample()).summaries;
}
