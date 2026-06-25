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
  assert.match(html, /启动同步/);
  assert.match(html, /创建评分批次/);
  assert.match(html, /启动评分/);
  assert.match(html, /同步 job #7 queued/);
  assert.match(html, /#10/);
  assert.match(html, /#11/);
});
