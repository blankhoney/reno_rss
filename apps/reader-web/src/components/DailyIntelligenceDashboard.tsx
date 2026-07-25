"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api/client";
import { listArticles, listAnnotationReviewQueue } from "@/lib/api/articles";
import { listClusters, listFeeds, listThemes } from "@/lib/api/intel";
import { ScoreRing } from "./ScoreRing";

type BriefItem = {
  article_id: number;
  title: string;
  rank?: number | null;
  tier?: string;
  rank_score?: number | null;
  reason?: string;
  summary_zh?: string | null;
  overall_score?: number | null;
  risk_flags?: string[];
  source_quality?: number | null;
  content_quality?: string | null;
};

type Brief = {
  generated_at?: string | null;
  title?: string;
  must_read?: BriefItem[];
  worth_scan?: BriefItem[];
  can_skip?: BriefItem[];
  source?: string;
};

type EntryCard = {
  id: string;
  title: string;
  hint: string;
  href: string;
  count: number;
  preview: string[];
  error?: string;
};

const TIERS: Array<{ key: keyof Brief; label: string; hint: string }> = [
  { key: "must_read", label: "今日必读", hint: "高信号，优先精读" },
  { key: "worth_scan", label: "值得扫", hint: "有价值，可快速浏览" },
  { key: "can_skip", label: "可忽略", hint: "低优先级或高不确定" },
];

export function DailyIntelligenceDashboard() {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshToken, setRefreshToken] = useState(0);
  const [entries, setEntries] = useState<EntryCard[]>([]);
  const [clustersError, setClustersError] = useState<string | null>(null);
  const [themesError, setThemesError] = useState<string | null>(null);
  const [sourceQualityError, setSourceQualityError] = useState<string | null>(null);
  const [clusters, setClusters] = useState<
    Array<{ id: string; label: string; size: number; mainArticleId: number }>
  >([]);
  const [themes, setThemes] = useState<Array<{ label: string; weight: number }>>([]);
  const [sourceQuality, setSourceQuality] = useState<{
    hidden: Array<{ id: number; title: string }>;
    highQuality: Array<{ id: number; title: string; qualityScore: number }>;
    needsAttention: Array<{
      id: number;
      title: string;
      userPriority: number;
      qualityScore: number;
    }>;
    active: number;
  }>({ hidden: [], highQuality: [], needsAttention: [], active: 0 });

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setClustersError(null);
    setThemesError(null);
    setSourceQualityError(null);

    Promise.allSettled([
      apiGet<{ brief?: Brief | null }>("/api/briefs/latest"),
      listArticles({ limit: 5, module: "read-later" }),
      listArticles({ limit: 5, module: "project" }),
      listAnnotationReviewQueue(5),
      listClusters(8),
      listThemes(8),
      listFeeds(),
    ])
      .then((results) => {
        if (!active) return;
        const [
          briefResult,
          continueResult,
          projectResult,
          reviewResult,
          clusterResult,
          themeResult,
          feedResult,
        ] = results;

        if (briefResult.status === "fulfilled") {
          setBrief(briefResult.value.brief ?? null);
          setError(null);
        } else {
          setError(
            briefResult.reason instanceof Error
              ? briefResult.reason.message
              : "情报加载失败",
          );
        }

        const continueItems =
          continueResult.status === "fulfilled" ? continueResult.value.articles : [];
        const projectItems =
          projectResult.status === "fulfilled" ? projectResult.value.articles : [];
        const reviewItems =
          reviewResult.status === "fulfilled" ? reviewResult.value : [];
        const resultError = (result: PromiseSettledResult<unknown>, fallback: string) =>
          result.status === "rejected"
            ? result.reason instanceof Error
              ? result.reason.message
              : fallback
            : undefined;

        setEntries([
          {
            id: "continue",
            title: "继续阅读",
            hint: "已开始，尚未读完",
            href: "?module=read-later&sort=default&lang=zh",
            count: continueItems.length,
            preview: continueItems.slice(0, 3).map((item) => item.title),
            error: resultError(continueResult, "继续阅读加载失败"),
          },
          {
            id: "project",
            title: "未完成项目",
            hint: "已立项队列",
            href: "?module=project&sort=default&lang=zh",
            count: projectItems.length,
            preview: projectItems.slice(0, 3).map((item) => item.title),
            error: resultError(projectResult, "立项队列加载失败"),
          },
          {
            id: "review",
            title: "待复习划线",
            hint: "间隔复习到期项",
            href: "?module=review&sort=default&lang=zh",
            count: reviewItems.length,
            preview: reviewItems
              .slice(0, 3)
              .map((item) => item.selectedText?.trim() || item.content)
              .filter(Boolean),
            error: resultError(reviewResult, "复习队列加载失败"),
          },
        ]);

        if (clusterResult.status === "fulfilled") {
          setClusters(
            clusterResult.value.map((item) => ({
              id: item.id,
              label: item.label,
              size: item.size,
              mainArticleId: item.mainArticleId,
            })),
          );
        } else {
          setClustersError(resultError(clusterResult, "主题簇加载失败") ?? "主题簇加载失败");
        }
        if (themeResult.status === "fulfilled") {
          setThemes(
            themeResult.value.map((item) => ({
              label: item.label,
              weight: item.weight,
            })),
          );
        } else {
          setThemesError(resultError(themeResult, "主题热度加载失败") ?? "主题热度加载失败");
        }
        if (feedResult.status === "fulfilled") {
          const feeds = feedResult.value;
          const hidden = feeds
            .filter((feed) => feed.hidden)
            .slice(0, 6)
            .map((feed) => ({ id: feed.id, title: feed.title }));
          const highQuality = feeds
            .filter((feed) => !feed.hidden && feed.qualityScore >= 80)
            .sort((a, b) => b.qualityScore - a.qualityScore)
            .slice(0, 6)
            .map((feed) => ({
              id: feed.id,
              title: feed.title,
              qualityScore: feed.qualityScore,
            }));
          const needsAttention = feeds
            .filter((feed) => !feed.hidden && (feed.userPriority < 0 || feed.qualityScore < 50))
            .sort((a, b) => a.qualityScore - b.qualityScore || a.userPriority - b.userPriority)
            .slice(0, 6)
            .map((feed) => ({
              id: feed.id,
              title: feed.title,
              userPriority: feed.userPriority,
              qualityScore: feed.qualityScore,
            }));
          setSourceQuality({
            hidden,
            highQuality,
            needsAttention,
            active: feeds.filter((feed) => !feed.hidden).length,
          });
        } else {
          setSourceQualityError(resultError(feedResult, "源可信度加载失败") ?? "源可信度加载失败");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [refreshToken]);

  return (
    <section className="dailyIntelPane" aria-label="今日情报台">
      <header className="articleListHeader">
        <div>
          <h1 className="articleListTitle">{brief?.title || "今日情报"}</h1>
          <p className="workbenchRibbonMuted">
            研究仪表 · 不是原始 RSS 时间线
            {brief?.generated_at ? ` · ${String(brief.generated_at).slice(0, 16)}` : ""}
            {brief?.source ? ` · ${brief.source}` : ""}
          </p>
        </div>
        <div className="articleListActions">
          <button type="button" className="readerToolbarBtn" disabled={loading} onClick={() => setRefreshToken((value) => value + 1)}>
            {loading ? "加载中" : "刷新情报"}
          </button>
          <Link className="readerToolbarBtn" href="?module=clusters&sort=default&lang=zh" prefetch={false}>
            故事线
          </Link>
          <Link className="readerToolbarBtn" href="?module=rules&sort=default&lang=zh" prefetch={false}>
            规则
          </Link>
          <Link className="readerToolbarBtn" href="?module=all&sort=default&lang=zh" prefetch={false}>
            打开全部订阅
          </Link>
          <Link
            className="readerToolbarBtn readerToolbarBtnPrimary"
            href="?module=review&sort=default&lang=zh"
            prefetch={false}
          >
            划线复习
          </Link>
        </div>
      </header>

      <section className="dailyIntelEntries" aria-label="持久入口">
        {entries.map((entry) => (
          <Link key={entry.id} className="dailyIntelEntryCard" href={entry.href} prefetch={false}>
            <div className="dailyIntelEntryTop">
              <h2>{entry.title}</h2>
              <span className="dailyIntelEntryCount">{entry.count}</span>
            </div>
            <p className="workbenchRibbonMuted">{entry.hint}</p>
            {loading ? (
              <p className="workbenchRibbonMuted">加载中…</p>
            ) : entry.error ? (
              <p className="adminConsoleError">加载失败：{entry.error}</p>
            ) : entry.preview.length > 0 ? (
              <ul className="dailyIntelEntryPreview">
                {entry.preview.map((line) => (
                  <li key={`${entry.id}-${line.slice(0, 24)}`}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="workbenchRibbonMuted">暂无条目</p>
            )}
          </Link>
        ))}
      </section>

      <section className="dailyIntelRadar" aria-label="异常与机会雷达">
        <header className="dailyIntelTierHeader">
          <h2>异常与机会雷达</h2>
          <span className="workbenchRibbonMuted">主题簇 · 重复风暴信号</span>
        </header>
        <div className="dailyIntelRadarGrid">
          <div className="dailyIntelRadarPane">
            <h3>突发主题簇</h3>
            {loading ? (
              <p className="workbenchRibbonMuted">加载中…</p>
            ) : clustersError ? (
              <p className="adminConsoleError">主题簇加载失败：{clustersError}</p>
            ) : clusters.length === 0 ? (
              <p className="workbenchRibbonMuted">暂无聚类；评分后会出现多源故事线。</p>
            ) : (
              <ul className="dailyIntelRadarList">
                {clusters.map((cluster) => (
                  <li key={cluster.id}>
                    <Link
                      href={`/read/${cluster.mainArticleId}?module=home&sort=default&lang=zh`}
                      prefetch={false}
                    >
                      {cluster.label}
                      <span className="workbenchRibbonMuted"> · {cluster.size} 源</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="dailyIntelRadarPane">
            <h3>主题热度</h3>
            {loading ? (
              <p className="workbenchRibbonMuted">加载中…</p>
            ) : themesError ? (
              <p className="adminConsoleError">加载失败：{themesError}</p>
            ) : themes.length === 0 ? (
              <p className="workbenchRibbonMuted">尚无标签主题。</p>
            ) : (
              <ul className="dailyIntelRadarList">
                {themes.map((theme) => (
                  <li key={theme.label}>
                    <Link
                      href={`?module=themes&sort=default&lang=zh`}
                      prefetch={false}
                    >
                      {theme.label}
                      <span className="workbenchRibbonMuted"> · w={theme.weight.toFixed(1)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      <section className="dailyIntelSourceQuality" aria-label="源可信度">
        <header className="dailyIntelTierHeader">
          <h2>源可信度</h2>
          <span className="workbenchRibbonMuted">
            活跃 {sourceQuality.active} · 高质量 {sourceQuality.highQuality.length} · 需关注{" "}
            {sourceQuality.needsAttention.length} · 隐藏 {sourceQuality.hidden.length}
          </span>
        </header>
        <div className="dailyIntelRadarGrid">
          <div className="dailyIntelRadarPane">
            <h3>已 demote / 隐藏</h3>
            {loading ? (
              <p className="workbenchRibbonMuted">加载中…</p>
            ) : sourceQualityError ? (
              <p className="adminConsoleError">加载失败：{sourceQualityError}</p>
            ) : sourceQuality.hidden.length === 0 ? (
              <p className="workbenchRibbonMuted">没有隐藏源。</p>
            ) : (
              <ul className="dailyIntelRadarList">
                {sourceQuality.hidden.map((feed) => (
                  <li key={feed.id}>{feed.title}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="dailyIntelRadarPane">
            <h3>高质量源机会</h3>
            {loading ? (
              <p className="workbenchRibbonMuted">加载中…</p>
            ) : sourceQualityError ? (
              <p className="adminConsoleError">加载失败：{sourceQualityError}</p>
            ) : sourceQuality.highQuality.length === 0 ? (
              <p className="workbenchRibbonMuted">尚无质量分 ≥80 的源。</p>
            ) : (
              <ul className="dailyIntelRadarList">
                {sourceQuality.highQuality.map((feed) => (
                  <li key={feed.id}>
                    {feed.title}
                    <span className="workbenchRibbonMuted"> · q={feed.qualityScore.toFixed(0)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="dailyIntelRadarPane">
            <h3>需关注源</h3>
            {loading ? (
              <p className="workbenchRibbonMuted">加载中…</p>
            ) : sourceQualityError ? (
              <p className="adminConsoleError">加载失败：{sourceQualityError}</p>
            ) : sourceQuality.needsAttention.length === 0 ? (
              <p className="workbenchRibbonMuted">没有低质量或负优先级源。</p>
            ) : (
              <ul className="dailyIntelRadarList">
                {sourceQuality.needsAttention.map((feed) => (
                  <li key={feed.id}>
                    {feed.title}
                    <span className="workbenchRibbonMuted">
                      {` · q=${feed.qualityScore.toFixed(0)} · p=${feed.userPriority}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      {loading ? <p className="workbenchRibbonMuted">正在生成情报视图…</p> : null}
      {error ? <p className="adminConsoleError">{error}</p> : null}
      {!loading && !error && brief == null ? (
        <div className="articleListEmpty">
          <p className="articleListEmptyTitle">尚无今日情报</p>
          <p className="articleListEmptyHint">
            管理员可触发评分 / 每日简报；有推荐版次后这里会自动分层展示。
          </p>
          <Link className="readerToolbarBtn" href="?module=admin&sort=default&lang=zh" prefetch={false}>
            前往管理台
          </Link>
        </div>
      ) : null}

      {brief
        ? TIERS.map((tier) => {
            const items = (brief[tier.key] as BriefItem[] | undefined) ?? [];
            return (
              <section key={tier.key} className="dailyIntelTier" aria-label={tier.label}>
                <header className="dailyIntelTierHeader">
                  <h2>{tier.label}</h2>
                  <span className="workbenchRibbonMuted">
                    {tier.hint} · {items.length}
                  </span>
                </header>
                {items.length === 0 ? (
                  <p className="workbenchRibbonMuted">本层暂无条目</p>
                ) : (
                  <ul className="dailyIntelList">
                    {items.map((item) => (
                      <li key={`${tier.key}-${item.article_id}`} className="dailyIntelCard">
                        <Link
                          className="dailyIntelCardLink"
                          href={`/read/${item.article_id}?module=home&sort=default&lang=zh`}
                          prefetch={false}
                        >
                          <div className="dailyIntelCardMain">
                            <div className="dailyIntelCardMeta">
                              {item.rank != null ? <span>#{item.rank}</span> : null}
                              {item.tier ? <span>{item.tier}</span> : null}
                              {item.risk_flags && item.risk_flags.length > 0 ? (
                                <span className="dailyIntelRisk">
                                  风险 {item.risk_flags.join("·")}
                                </span>
                              ) : null}
                              {item.source_quality != null ? (
                                <span title="来源质量维度">源可信 {Math.round(item.source_quality)}</span>
                              ) : null}
                              {item.content_quality ? (
                                <span title="正文质量">{item.content_quality}</span>
                              ) : null}
                            </div>
                            <h3 className="dailyIntelCardTitle">{item.title}</h3>
                            <p className="dailyIntelCardSummary">
                              {item.summary_zh?.trim() || item.reason || "暂无摘要"}
                            </p>
                            {item.reason ? (
                              <p className="dailyIntelCardReason" title={item.reason}>
                                为什么：{item.reason}
                              </p>
                            ) : null}
                          </div>
                          <ScoreRing
                            value={item.overall_score ?? item.rank_score ?? null}
                            tier={item.tier ?? null}
                            size={52}
                          />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })
        : null}
    </section>
  );
}
