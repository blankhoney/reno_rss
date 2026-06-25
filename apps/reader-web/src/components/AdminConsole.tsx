"use client";

import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import {
  createScoringBatch,
  enqueueAdminSync,
  getScoringBatch,
  startScoringBatch,
  type CandidateWindow,
  type ScoringBatch,
} from "@/lib/api/admin";
import { getCurrentSession } from "@/lib/api/auth";
import { pollJobUntilTerminal } from "@/lib/api/articles";

type AdminConsoleViewProps = {
  role: string | null;
  syncMessage: string | null;
  scoringMessage: string | null;
  error: string | null;
  isBusy: boolean;
  batch: ScoringBatch | null;
  onSync: (event: FormEvent<HTMLFormElement>) => void;
  onCreateBatch: (event: FormEvent<HTMLFormElement>) => void;
  onStartBatch: () => void;
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
  scoringMessage,
  error,
  isBusy,
  batch,
  onSync,
  onCreateBatch,
  onStartBatch,
}: AdminConsoleViewProps) {
  if (role === null) {
    return (
      <section className="adminConsolePane" aria-label="管理控制台" aria-busy="true">
        <header className="feedQualityHeader">
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
        <header className="feedQualityHeader">
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
      <header className="feedQualityHeader">
        <div>
          <h1>管理控制台</h1>
          <p>手动触发 Miniflux 同步和评分批次；真实 LLM provider 由后端环境控制。</p>
        </div>
      </header>

      {error ? <p className="feedQualityError">{error}</p> : null}

      <div className="adminConsoleGrid">
        <form className="adminConsoleCard" onSubmit={onSync}>
          <h2>同步文章</h2>
          <label className="authField">
            <span>同步上限</span>
            <input className="authTextInput" name="limit" type="number" min="1" max="500" defaultValue="100" />
          </label>
          <button type="submit" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={isBusy}>
            {isBusy ? "处理中" : "启动同步"}
          </button>
          {syncMessage ? <p className="adminConsoleMessage">{syncMessage}</p> : null}
        </form>

        <form className="adminConsoleCard" onSubmit={onCreateBatch}>
          <h2>评分批次</h2>
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
          <button type="submit" className="readerToolbarBtn readerToolbarBtnPrimary" disabled={isBusy}>
            {isBusy ? "处理中" : "创建评分批次"}
          </button>
          <button
            type="button"
            className="readerToolbarBtn"
            disabled={isBusy || batch == null}
            onClick={onStartBatch}
          >
            启动评分
          </button>
          {scoringMessage ? <p className="adminConsoleMessage">{scoringMessage}</p> : null}
        </form>
      </div>

      {batch ? (
        <section className="adminConsoleBatch" aria-label="当前评分批次">
          <h2>批次 #{batch.id}</h2>
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
      ) : null}
    </section>
  );
}

export function AdminConsole() {
  const [role, setRole] = useState<string | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [scoringMessage, setScoringMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [batch, setBatch] = useState<ScoringBatch | null>(null);

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

  async function handleSync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const limit = clampInt(form.get("limit"), 1, 500, 100);
    setIsBusy(true);
    setError(null);
    try {
      const created = await enqueueAdminSync({ limit });
      setSyncMessage(`同步 job #${created.jobId} ${created.status}`);
      const job = await pollJobUntilTerminal(created.jobId);
      setSyncMessage(`同步 job #${job.id} ${job.status}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "同步启动失败");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCreateBatch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsBusy(true);
    setError(null);
    try {
      const nextBatch = await createScoringBatch({
        name: String(form.get("name") ?? "").trim() || null,
        candidateWindow: String(form.get("candidateWindow") ?? "last_3_days") as CandidateWindow,
        articleIds: parseArticleIds(String(form.get("articleIds") ?? "")),
      });
      setBatch(nextBatch);
      setScoringMessage(`评分批次 #${nextBatch.id} 已创建`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "评分批次创建失败");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStartBatch() {
    if (batch == null) return;
    setIsBusy(true);
    setError(null);
    try {
      const started = await startScoringBatch(batch.id);
      setScoringMessage(`评分 job #${started.jobId} ${started.status}`);
      const job = await pollJobUntilTerminal(started.jobId);
      setScoringMessage(`评分 job #${job.id} ${job.status}`);
      setBatch(await getScoringBatch(batch.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "评分启动失败");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <AdminConsoleView
      role={role}
      syncMessage={syncMessage}
      scoringMessage={scoringMessage}
      error={error}
      isBusy={isBusy}
      batch={batch}
      onSync={(event) => void handleSync(event)}
      onCreateBatch={(event) => void handleCreateBatch(event)}
      onStartBatch={() => void handleStartBatch()}
    />
  );
}
