"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import {
  createScoringBatch,
  enqueueAdminSync,
  getAdminUsageToday,
  getPipelineHealth,
  getScoringBatch,
  startScoringBatch,
  type AdminUsageToday,
  type PipelineHealth,
  type CandidateWindow,
  type ScoringBatch,
} from "@/lib/api/admin";
import { getCurrentSession } from "@/lib/api/auth";
import {
  getArticleStats,
  pollJobUntilTerminal,
  type ArticleStats,
} from "@/lib/api/articles";

type AdminConsoleViewProps = {
  role: string | null;
  syncMessage: string | null;
  syncError: string | null;
  scoringMessage: string | null;
  scoringError: string | null;
  isSyncBusy: boolean;
  isScoringBusy: boolean;
  batch: ScoringBatch | null;
  stats: ArticleStats | null;
  statsError: string | null;
  usage: AdminUsageToday | null;
  usageError: string | null;
  pipelineHealth: PipelineHealth | null;
  pipelineError: string | null;
  isStatsLoading?: boolean;
  isUsageLoading?: boolean;
  isPipelineLoading?: boolean;
  onRetryStats: () => void;
  onRetryUsage: () => void;
  onRetryPipeline: () => void;
  onSync: (event: FormEvent<HTMLFormElement>) => void;
  onCreateBatch: (event: FormEvent<HTMLFormElement>) => void;
  onStartBatch: () => void;
};

const PIPELINE_STATUS_LABELS: Record<PipelineHealth["status"], string> = {
  healthy: "健康",
  degraded: "需处理",
  idle: "等待首次运行",
  paused: "已暂停",
};

function clampInt(value: unknown, min: number, max: number, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function parseArticleIds(raw: string): number[] {
  const ids = [
    ...new Set(
      raw
        .split(/[,\s]+/)
        .map((part) => Number.parseInt(part, 10))
        .filter((value) => Number.isInteger(value) && value > 0),
    ),
  ];
  if (ids.length === 0) throw new Error("请输入至少 1 个文章 ID");
  if (ids.length > 30) throw new Error("评分批次最多 30 篇文章");
  return ids;
}

function candidateWindowLabel(value: CandidateWindow): string {
  if (value === "today") return "今天";
  if (value === "last_3_days") return "最近 3 天";
  return "自定义";
}

export function AdminConsoleView({
  role,
  syncMessage,
  syncError,
  scoringMessage,
  scoringError,
  isSyncBusy,
  isScoringBusy,
  batch,
  stats,
  statsError,
  usage,
  usageError,
  pipelineHealth,
  pipelineError,
  isStatsLoading = false,
  isUsageLoading = false,
  isPipelineLoading = false,
  onRetryStats,
  onRetryUsage,
  onRetryPipeline,
  onSync,
  onCreateBatch,
  onStartBatch,
}: AdminConsoleViewProps) {
  if (role === null) {
    return (
      <section className="adminConsolePane" aria-label="管理控制台" aria-busy="true">
        <header className="adminConsoleHeader">
          <div>
            <h1>管理控制台</h1>
            <p>正在验证管理员权限。</p>
          </div>
        </header>
      </section>
    );
  }

  if (role !== "admin") {
    return (
      <section className="adminConsolePane" aria-label="管理控制台">
        <header className="adminConsoleHeader">
          <div>
            <h1>管理控制台</h1>
            <p>需要管理员权限才能执行同步和评分任务。</p>
          </div>
        </header>
      </section>
    );
  }

  return (
    <section className="adminConsolePane" aria-label="管理控制台">
      <header className="adminConsoleHeader">
        <div>
          <h1>管理控制台</h1>
          <p>手动触发 Miniflux 同步和评分批次；真实 LLM provider 由后端环境控制。</p>
        </div>
      </header>

      <div className="adminConsoleGrid">
        <section className="adminConsoleCard" aria-label="今日费用">
          <header className="adminConsoleCardHeader">
            <div>
              <h2>今日费用</h2>
              <p className="adminConsoleStat">
                {usage
                  ? `${usage.day} · Score ${usage.accounts.score.used}/${usage.accounts.score.limit || "∞"} · Ask ${usage.accounts.ask.used}/${usage.accounts.ask.limit || "∞"} · Agent ${usage.accounts.agent.used}/${usage.accounts.agent.limit || "∞"}`
                  : isUsageLoading
                    ? "费用加载中"
                    : usageError
                      ? "费用加载失败"
                      : "费用暂不可用"}
              </p>
            </div>
          </header>
          {usage ? (
            <ul className="adminUsageList">
              {(["score", "ask", "agent"] as const).map((name) => {
                const account = usage.accounts[name];
                const label = name === "score" ? "Score" : name === "ask" ? "Ask" : "Agent";
                return (
                  <li key={name}>
                    {label}: <strong>{account.used}{account.limit > 0 ? ` / ${account.limit}` : " / 不限"}</strong>
                    {account.remaining != null ? (
                      <span className="adminConsoleStat"> · 剩余 {account.remaining}</span>
                    ) : null}
                  </li>
                );
              })}
              <li className="adminConsoleStat">
                Score 以评分 DB 为真源；Ask/Agent 为{usage.accounting}共享账本。
              </li>
              <li className="adminConsoleStat">云控制台账户上限仍是最后一道硬闸。</li>
            </ul>
          ) : usageError ? (
            <p className="adminConsoleError" role="alert">
              费用加载失败：{usageError}
              <button type="button" className="readerToolbarBtn" onClick={onRetryUsage} disabled={isUsageLoading}>
                重试
              </button>
            </p>
          ) : (
            <p className="adminConsoleEmpty">无法读取 /api/admin/usage/today。</p>
          )}
        </section>

        <section className="adminConsoleCard" aria-label="批量评分">
          <header className="adminConsoleCardHeader">
            <div>
              <h2>批量评分</h2>
              <p className="adminConsoleStat">
                {isStatsLoading
                  ? "统计加载中"
                  : stats
                    ? `${stats.unscored} 篇待评分`
                    : statsError
                      ? "统计加载失败"
                      : "统计暂不可用"}
              </p>
            </div>
          </header>
          {statsError ? (
            <p className="adminConsoleError" role="alert">
              统计加载失败：{statsError}
              <button type="button" className="readerToolbarBtn" onClick={onRetryStats} disabled={isStatsLoading}>
                重试
              </button>
            </p>
          ) : null}
          <form className="adminConsoleForm" onSubmit={onCreateBatch}>
            <label className="authField">
              <span>名称</span>
              <input className="authTextInput" name="name" placeholder="Today" />
            </label>
            <label className="authField">
              <span>候选窗口</span>
              <select className="authTextInput" name="candidateWindow" defaultValue="last_3_days">
                <option value="today">今天</option>
                <option value="last_3_days">最近 3 天</option>
                <option value="custom">自定义</option>
              </select>
            </label>
            <label className="authField">
              <span>文章 ID</span>
              <textarea className="authTextInput adminArticleIds" name="articleIds" placeholder="10, 11, 12" />
            </label>
            <div className="adminConsoleActions">
              <button type="submit" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={isScoringBusy}>
                {isScoringBusy ? "处理中" : "创建评分批次"}
              </button>
              <button
                type="button"
                className="readerToolbarBtn"
                disabled={isScoringBusy || batch == null}
                onClick={onStartBatch}
              >
                启动评分
              </button>
            </div>
          </form>
        </section>

        <section className="adminConsoleCard" aria-label="队列状态">
          <header className="adminConsoleCardHeader">
            <div>
              <h2>队列状态</h2>
              <p className="adminQueuePlaceholder">
                {pipelineHealth
                  ? `${pipelineHealth.schedulerEnabled ? "调度常开" : "调度暂停"} · ${PIPELINE_STATUS_LABELS[pipelineHealth.status]}`
                  : isPipelineLoading
                    ? "队列状态加载中"
                    : pipelineError
                      ? "队列状态加载失败"
                      : "队列状态暂不可用"}
              </p>
            </div>
          </header>
          {pipelineHealth ? (
            <div className="adminPipelineHealth" aria-label="自动情报管道状态">
              <p>
                排队 <strong>{pipelineHealth.queue.queued}</strong> · 运行中{" "}
                <strong>{pipelineHealth.queue.running}</strong> · 24h 失败{" "}
                <strong>{pipelineHealth.queue.failed24h}</strong> · 陈旧租约{" "}
                <strong>{pipelineHealth.queue.staleRunning}</strong>
              </p>
              <ul>
                {pipelineHealth.jobs.map((job) => (
                  <li key={job.jobType}>
                    {job.jobType}: <strong>{job.status}</strong>
                    {job.lastError ? ` · ${job.lastError}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : pipelineError ? (
            <p className="adminConsoleError" role="alert">
              队列状态加载失败：{pipelineError}
              <button type="button" className="readerToolbarBtn" onClick={onRetryPipeline} disabled={isPipelineLoading}>
                重试
              </button>
            </p>
          ) : null}
          <form className="adminConsoleForm adminSyncForm" onSubmit={onSync}>
            <label className="authField">
              <span>同步上限</span>
              <input className="authTextInput" name="limit" type="number" min="1" max="500" defaultValue="100" />
            </label>
            <button type="submit" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={isSyncBusy}>
              {isSyncBusy ? "处理中" : "启动同步"}
            </button>
          </form>
          {syncMessage ? <p className="adminConsoleMessage">{syncMessage}</p> : null}
          {syncError ? <p className="adminConsoleError" role="alert">同步失败：{syncError}</p> : null}
          {scoringMessage ? <p className="adminConsoleMessage">{scoringMessage}</p> : null}
          {scoringError ? <p className="adminConsoleError" role="alert">评分失败：{scoringError}</p> : null}
          {batch ? (
            <section className="adminConsoleBatch" aria-label="当前评分批次">
              <h3>批次 #{batch.id}</h3>
              <p>
                {batch.name ?? "未命名"} / {candidateWindowLabel(batch.candidateWindow)} / {batch.status} /{" "}
                {batch.articleCount} 篇
              </p>
              <ul>
                {batch.items.map((item) => (
                  <li key={item.id}>
                    #{item.articleId} {item.status}
                    {item.error ? ` / ${item.error}` : ""}
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <p className="adminConsoleEmpty">当前没有评分批次。</p>
          )}
        </section>
      </div>
    </section>
  );
}

export function AdminConsole() {
  const [role, setRole] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [scoringMessage, setScoringMessage] = useState<string | null>(null);
  const [scoringError, setScoringError] = useState<string | null>(null);
  const [isSyncBusy, setIsSyncBusy] = useState(false);
  const [isScoringBusy, setIsScoringBusy] = useState(false);
  const [batch, setBatch] = useState<ScoringBatch | null>(null);
  const [stats, setStats] = useState<ArticleStats | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [isStatsLoading, setIsStatsLoading] = useState(false);
  const [usage, setUsage] = useState<AdminUsageToday | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [isUsageLoading, setIsUsageLoading] = useState(false);
  const [pipelineHealth, setPipelineHealth] = useState<PipelineHealth | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [isPipelineLoading, setIsPipelineLoading] = useState(false);

  const refreshStats = useCallback(async () => {
    setIsStatsLoading(true);
    setStatsError(null);
    try {
      setStats(await getArticleStats());
    } catch (caught) {
      setStats(null);
      setStatsError(caught instanceof Error ? caught.message : "统计加载失败");
    } finally {
      setIsStatsLoading(false);
    }
  }, []);

  const refreshUsage = useCallback(async () => {
    setIsUsageLoading(true);
    setUsageError(null);
    try {
      setUsage(await getAdminUsageToday());
    } catch (caught) {
      setUsage(null);
      setUsageError(caught instanceof Error ? caught.message : "费用加载失败");
    } finally {
      setIsUsageLoading(false);
    }
  }, []);

  const refreshPipeline = useCallback(async () => {
    setIsPipelineLoading(true);
    setPipelineError(null);
    try {
      setPipelineHealth(await getPipelineHealth());
    } catch (caught) {
      setPipelineHealth(null);
      setPipelineError(caught instanceof Error ? caught.message : "队列状态加载失败");
    } finally {
      setIsPipelineLoading(false);
    }
  }, []);

  const refreshAdminSnapshots = useCallback(async () => {
    await Promise.all([refreshStats(), refreshUsage(), refreshPipeline()]);
  }, [refreshPipeline, refreshStats, refreshUsage]);

  useEffect(() => {
    let active = true;
    getCurrentSession()
      .then((session) => {
        if (active) setRole(session?.user.role ?? "user");
      })
      .catch(() => {
        if (active) setRole("user");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (role !== "admin") {
      setStats(null);
      setUsage(null);
      setPipelineHealth(null);
      return;
    }
    void refreshAdminSnapshots();
  }, [refreshAdminSnapshots, role]);

  async function handleSync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const limit = clampInt(form.get("limit"), 1, 500, 100);
    setIsSyncBusy(true);
    setSyncError(null);
    try {
      const created = await enqueueAdminSync({ limit });
      setSyncMessage(`同步 job #${created.jobId} ${created.status}`);
      const job = await pollJobUntilTerminal(created.jobId);
      setSyncMessage(`同步 job #${job.id} ${job.status}`);
      await refreshAdminSnapshots();
    } catch (caught) {
      setSyncError(caught instanceof Error ? caught.message : "同步启动失败");
    } finally {
      setIsSyncBusy(false);
    }
  }

  async function handleCreateBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsScoringBusy(true);
    setScoringError(null);
    try {
      const nextBatch = await createScoringBatch({
        name: String(form.get("name") ?? "").trim() || null,
        candidateWindow: String(form.get("candidateWindow") ?? "last_3_days") as CandidateWindow,
        articleIds: parseArticleIds(String(form.get("articleIds") ?? "")),
      });
      setBatch(nextBatch);
      setScoringMessage(`评分批次 #${nextBatch.id} 已创建`);
      await refreshAdminSnapshots();
    } catch (caught) {
      setScoringError(caught instanceof Error ? caught.message : "评分批次创建失败");
    } finally {
      setIsScoringBusy(false);
    }
  }

  async function handleStartBatch() {
    if (batch == null) return;
    setIsScoringBusy(true);
    setScoringError(null);
    try {
      const started = await startScoringBatch(batch.id);
      setScoringMessage(`评分 job #${started.jobId} ${started.status}`);
      const job = await pollJobUntilTerminal(started.jobId);
      setScoringMessage(`评分 job #${job.id} ${job.status}`);
      setBatch(await getScoringBatch(batch.id));
      await refreshAdminSnapshots();
    } catch (caught) {
      setScoringError(caught instanceof Error ? caught.message : "评分启动失败");
    } finally {
      setIsScoringBusy(false);
    }
  }

  return (
    <AdminConsoleView
      role={role}
      syncMessage={syncMessage}
      syncError={syncError}
      scoringMessage={scoringMessage}
      scoringError={scoringError}
      isSyncBusy={isSyncBusy}
      isScoringBusy={isScoringBusy}
      batch={batch}
      stats={stats}
      statsError={statsError}
      usage={usage}
      usageError={usageError}
      pipelineHealth={pipelineHealth}
      pipelineError={pipelineError}
      isStatsLoading={isStatsLoading}
      isUsageLoading={isUsageLoading}
      isPipelineLoading={isPipelineLoading}
      onRetryStats={() => void refreshStats()}
      onRetryUsage={() => void refreshUsage()}
      onRetryPipeline={() => void refreshPipeline()}
      onSync={(event) => void handleSync(event)}
      onCreateBatch={(event) => void handleCreateBatch(event)}
      onStartBatch={() => void handleStartBatch()}
    />
  );
}
