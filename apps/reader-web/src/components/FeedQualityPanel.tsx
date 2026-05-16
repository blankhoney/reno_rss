"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { FeedQualitySummary } from "@/lib/feeds/quality";

type FeedQualityResponse = {
  feeds: FeedQualitySummary[];
};

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function qualityLabel(score: number): string {
  if (score >= 70) return "高价值";
  if (score >= 45) return "普通";
  return "低质量";
}

async function updateHidden(feedId: number, hidden: boolean) {
  const response = await fetch(`/api/feeds/${feedId}/preference`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hidden }),
  });
  if (!response.ok) throw new Error("feed_preference_failed");
}

export function FeedQualityPanel() {
  const router = useRouter();
  const [feeds, setFeeds] = useState<FeedQualitySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingFeedId, setPendingFeedId] = useState<number | null>(null);

  async function loadFeeds() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/feeds/quality", { cache: "no-store" });
      if (!response.ok) throw new Error("feed_quality_failed");
      const data = (await response.json()) as FeedQualityResponse;
      setFeeds(data.feeds);
    } catch {
      setError("订阅源质量读取失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadFeeds();
  }, []);

  async function toggleFeed(feed: FeedQualitySummary) {
    setPendingFeedId(feed.id);
    setError(null);
    try {
      await updateHidden(feed.id, !feed.hidden);
      setFeeds((current) =>
        current.map((item) => (item.id === feed.id ? { ...item, hidden: !feed.hidden } : item)),
      );
      router.refresh();
    } catch {
      setError("订阅源状态保存失败");
    } finally {
      setPendingFeedId(null);
    }
  }

  return (
    <section className="feedQualityPane" aria-label="订阅源质量">
      <header className="feedQualityHeader">
        <div>
          <h1>订阅源质量</h1>
          <p>低质量源会在默认列表自动降权；手动隐藏后不再出现在默认信息流。</p>
        </div>
        <button type="button" className="readerToolbarBtn" disabled={loading} onClick={() => void loadFeeds()}>
          {loading ? "刷新中" : "刷新"}
        </button>
      </header>

      {error ? <p className="feedQualityError">{error}</p> : null}
      {loading && feeds.length === 0 ? <p className="feedQualityLoading">正在读取订阅源质量...</p> : null}

      <div className="feedQualityList">
        {feeds.map((feed) => {
          const fullRate = feed.articleCount > 0 ? feed.fullCount / feed.articleCount : 0;
          const blockedRate = feed.articleCount > 0 ? feed.blockedCount / feed.articleCount : 0;
          return (
            <article
              key={feed.id}
              className={`feedQualityCard${feed.hidden ? " feedQualityCardHidden" : ""}`}
            >
              <div className="feedQualityMain">
                <div>
                  <h2>{feed.title || `Feed ${feed.id}`}</h2>
                  <p className="feedQualityMeta">
                    #{feed.id} · {qualityLabel(feed.qualityScore)} · 质量 {feed.qualityScore}
                  </p>
                </div>
                <button
                  type="button"
                  className="readerToolbarBtn"
                  disabled={pendingFeedId === feed.id}
                  onClick={() => void toggleFeed(feed)}
                >
                  {pendingFeedId === feed.id ? "保存中" : feed.hidden ? "恢复" : "隐藏"}
                </button>
              </div>
              <dl className="feedQualityStats">
                <div>
                  <dt>样本</dt>
                  <dd>{feed.articleCount}</dd>
                </div>
                <div>
                  <dt>完整率</dt>
                  <dd>{percent(fullRate)}</dd>
                </div>
                <div>
                  <dt>错误页</dt>
                  <dd>{percent(blockedRate)}</dd>
                </div>
                <div>
                  <dt>均分</dt>
                  <dd>{feed.averageScore ?? "未评分"}</dd>
                </div>
                <div>
                  <dt>高分</dt>
                  <dd>{feed.highScoreCount}</dd>
                </div>
                <div>
                  <dt>行为</dt>
                  <dd>
                    {feed.starredCount + feed.readLaterCount + feed.projectCount + feed.readCount}
                  </dd>
                </div>
              </dl>
              <p className="feedQualityReasons">
                {feed.reasons.length > 0 ? feed.reasons.join(" / ") : "暂无质量信号"}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
