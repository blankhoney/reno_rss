import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { AdminConsoleView } from "./AdminConsole";

test("AdminConsoleView hides admin controls from non-admin users", () => {
  const html = renderToStaticMarkup(
    React.createElement(AdminConsoleView, {
      role: "user",
      syncMessage: null,
      syncError: null,
      scoringMessage: null,
      scoringError: null,
      isSyncBusy: false,
      isScoringBusy: false,
      batch: null,
      stats: null,
      statsError: null,
      usage: null,
      usageError: null,
      pipelineHealth: null,
      pipelineError: null,
      onRetryStats: () => {},
      onRetryUsage: () => {},
      onRetryPipeline: () => {},
      onSync: () => {},
      onCreateBatch: () => {},
      onStartBatch: () => {},
    }),
  );

  assert.match(html, /需要管理员权限/);
  assert.doesNotMatch(html, /启动同步/);
  assert.doesNotMatch(html, /创建评分批次/);
});

test("AdminConsoleView renders admin sync and scoring controls", () => {
  const html = renderToStaticMarkup(
    React.createElement(AdminConsoleView, {
      role: "admin",
      syncMessage: "同步 job #7 queued",
      syncError: null,
      scoringMessage: "评分批次已创建",
      scoringError: null,
      isSyncBusy: false,
      isScoringBusy: false,
      stats: {
        total: 30,
        scored: 22,
        unscored: 8,
      },
      statsError: null,
      isStatsLoading: false,
      usage: {
        day: "2026-07-18",
        scoresCountToday: 12,
        scoresAccounting: "database",
        askUsed: 3,
        askLimit: 100,
        askRemaining: 97,
        askAccounting: "process_memory",
        accounts: {
          score: { used: 12, limit: 60, remaining: 48 },
          ask: { used: 3, limit: 100, remaining: 97 },
          agent: { used: 2, limit: 20, remaining: 18 },
        },
        accounting: "database",
      },
      usageError: null,
      isUsageLoading: false,
      pipelineHealth: {
        status: "degraded",
        schedulerEnabled: true,
        queue: {
          queued: 2,
          running: 1,
          failed24h: 1,
          staleRunning: 0,
          oldestQueuedAt: "2026-07-18T08:00:00Z",
        },
        jobs: [
          {
            jobType: "sync_miniflux_entries",
            status: "failed",
            updatedAt: "2026-07-18T09:00:00Z",
            lastError: "timeout",
          },
        ],
      },
      pipelineError: null,
      isPipelineLoading: false,
      batch: {
        id: 3,
        name: "Today",
        status: "queued",
        triggerType: "manual",
        candidateWindow: "today",
        articleCount: 2,
        createdBy: "admin-id",
        createdAt: "2026-06-25T00:00:00Z",
        startedAt: null,
        finishedAt: null,
        items: [
          { id: 1, batchId: 3, articleId: 10, status: "queued", baseScoreId: null, error: null },
          { id: 2, batchId: 3, articleId: 11, status: "queued", baseScoreId: null, error: null },
        ],
      },
      onRetryStats: () => {},
      onRetryUsage: () => {},
      onRetryPipeline: () => {},
      onSync: () => {},
      onCreateBatch: () => {},
      onStartBatch: () => {},
    }),
  );

  assert.match(html, /管理控制台/);
  assert.equal((html.match(/class="adminConsoleCard"/g) ?? []).length, 3);
  assert.match(html, /8 篇待评分/);
  assert.match(html, /今日费用/);
  assert.match(html, /Score.*12.*60/);
  assert.match(html, /Ask.*3.*100/);
  assert.match(html, /Agent.*2.*20/);
  assert.match(html, /调度常开 · 需处理/);
  assert.match(html, /24h 失败/);
  assert.match(html, /sync_miniflux_entries/);
  assert.match(html, /启动同步/);
  assert.match(html, /创建评分批次/);
  assert.match(html, /启动评分/);
  assert.match(html, /同步 job #7 queued/);
  assert.match(html, /#10/);
  assert.match(html, /#11/);
});

test("AdminConsoleView keeps successful cards visible when usage fails and exposes retry", () => {
  const html = renderToStaticMarkup(
    React.createElement(AdminConsoleView, {
      role: "admin",
      syncMessage: null,
      syncError: null,
      scoringMessage: null,
      scoringError: null,
      isSyncBusy: false,
      isScoringBusy: false,
      batch: null,
      stats: { total: 10, scored: 7, unscored: 3 },
      statsError: null,
      usage: null,
      usageError: "usage fixture failure",
      pipelineHealth: {
        status: "healthy",
        schedulerEnabled: true,
        queue: { queued: 0, running: 0, failed24h: 0, staleRunning: 0, oldestQueuedAt: null },
        jobs: [],
      },
      pipelineError: null,
      onRetryStats: () => {},
      onRetryUsage: () => {},
      onRetryPipeline: () => {},
      onSync: () => {},
      onCreateBatch: () => {},
      onStartBatch: () => {},
    }),
  );

  assert.match(html, /3 篇待评分/);
  assert.match(html, /调度常开 · 健康/);
  assert.match(html, /费用加载失败：usage fixture failure/);
  assert.match(html, />重试</);
  assert.doesNotMatch(html, /队列状态加载中/);
});
