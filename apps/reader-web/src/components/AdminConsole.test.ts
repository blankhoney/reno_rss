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
      scoringMessage: null,
      error: null,
      isBusy: false,
      batch: null,
      stats: null,
      usage: null,
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
      scoringMessage: "评分批次已创建",
      error: null,
      isBusy: false,
      stats: {
        total: 30,
        scored: 22,
        unscored: 8,
      },
      usage: {
        day: "2026-07-18",
        scoresCountToday: 12,
        scoresAccounting: "database",
        askUsed: 3,
        askLimit: 100,
        askRemaining: 97,
        askAccounting: "process_memory",
      },
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
      onSync: () => {},
      onCreateBatch: () => {},
      onStartBatch: () => {},
    }),
  );

  assert.match(html, /管理控制台/);
  assert.equal((html.match(/class="adminConsoleCard"/g) ?? []).length, 3);
  assert.match(html, /8 篇待评分/);
  assert.match(html, /今日费用/);
  assert.match(html, /评分 12 次/);
  assert.match(html, /Ask 3\/100/);
  assert.match(html, /翻译任务由文章页触发,无全局队列视图/);
  assert.match(html, /启动同步/);
  assert.match(html, /创建评分批次/);
  assert.match(html, /启动评分/);
  assert.match(html, /同步 job #7 queued/);
  assert.match(html, /#10/);
  assert.match(html, /#11/);
});
