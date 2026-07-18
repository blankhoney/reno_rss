"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api/client";
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
};

type Brief = {
  generated_at?: string | null;
  title?: string;
  must_read?: BriefItem[];
  worth_scan?: BriefItem[];
  can_skip?: BriefItem[];
  source?: string;
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

  useEffect(() => {
    let active = true;
    setLoading(true);
    apiGet<{ brief?: Brief | null }>("/api/briefs/latest")
      .then((payload) => {
        if (!active) return;
        setBrief(payload.brief ?? null);
        setError(null);
      })
      .catch((caught) => {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "情报加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

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
          <Link className="readerToolbarBtn" href="?module=all&sort=default&lang=zh" prefetch={false}>
            打开全部订阅
          </Link>
          <Link className="readerToolbarBtn readerToolbarBtnPrimary" href="?module=review&sort=default&lang=zh" prefetch={false}>
            划线复习
          </Link>
        </div>
      </header>

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
                  <span className="workbenchRibbonMuted">{tier.hint} · {items.length}</span>
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
                                <span className="dailyIntelRisk">风险 {item.risk_flags.join("·")}</span>
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
