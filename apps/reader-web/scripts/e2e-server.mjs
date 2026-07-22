import { createServer, request as upstreamRequest } from "node:http";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const proxyPort = 3010;
const appPort = 3011;
const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const users = {
  ada: {
    id: "user-a",
    display_name: "Ada",
    role: "user",
    created_at: "2026-07-21T00:00:00Z",
    last_seen_at: null,
  },
  babbage: {
    id: "user-b",
    display_name: "Babbage",
    role: "user",
    created_at: "2026-07-21T00:00:00Z",
    last_seen_at: null,
  },
  admin: {
    id: "admin-a",
    display_name: "Admin Ada",
    role: "admin",
    created_at: "2026-07-22T00:00:00Z",
    last_seen_at: null,
  },
};

let currentUser = users.ada;
let jobRequestCount = 0;
let usageFailuresRemaining = 0;
let adminSyncCompleted = false;
const completedResearchJob = {
  id: 88,
  job_type: "research",
  status: "succeeded",
  progress: { completed: 1, total: 1 },
  result: {
    brief: {
      answer: "## 本周研究\n\n优先跟进检索质量。",
      citations: [{ article_id: 7, title: "Keyboard article one", quote: "检索质量" }],
      provider: "mock",
      question: "本周重点是什么？",
    },
  },
  last_error: null,
  created_at: "2026-07-22T00:00:00Z",
  updated_at: "2026-07-22T00:01:00Z",
  completed_at: "2026-07-22T00:01:00Z",
};

function sendJson(response, status, payload) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

function sendJsonAfter(response, status, payload, delayMs) {
  setTimeout(() => sendJson(response, status, payload), delayMs);
}

function resetFixtures() {
  currentUser = users.ada;
  jobRequestCount = 0;
  usageFailuresRemaining = 0;
  adminSyncCompleted = false;
}

function proxyToApp(request, response) {
  const upstream = upstreamRequest(
    {
      hostname: "127.0.0.1",
      port: appPort,
      path: request.url,
      method: request.method,
      headers: request.headers,
    },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    },
  );
  upstream.on("error", () => {
    response.writeHead(502, { "content-type": "text/plain" });
    response.end("E2E upstream unavailable");
  });
  request.pipe(upstream);
}

const app = spawn(process.execPath, ["server.js"], {
  cwd: resolve(rootDir, ".next/standalone"),
  env: { ...process.env, HOSTNAME: "127.0.0.1", PORT: String(appPort) },
  stdio: "inherit",
});

const proxy = createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${proxyPort}`);

  if (url.pathname === "/__e2e/reset" && request.method === "POST") {
    resetFixtures();
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/__e2e/admin" && request.method === "POST") {
    currentUser = users.admin;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/__e2e/admin/usage-fail-once" && request.method === "POST") {
    currentUser = users.admin;
    usageFailuresRemaining = 1;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/api/auth/me" && request.method === "GET") {
    sendJson(response, 200, { user: currentUser });
    return;
  }
  if (url.pathname === "/api/auth/login" && request.method === "POST") {
    currentUser = users.babbage;
    sendJson(response, 200, { user: currentUser });
    return;
  }
  if (url.pathname === "/api/auth/logout" && request.method === "POST") {
    sendJson(response, 204, undefined);
    return;
  }
  if (url.pathname === "/api/articles" && request.method === "GET") {
    const searchQuery = url.searchParams.get("q");
    if (searchQuery === "workbench-error") {
      sendJson(response, 500, { error: { message: "workbench fixture failure" } });
      return;
    }
    if (searchQuery === "annotations-only") {
      sendJson(response, 500, { error: { message: "article fixture failure" } });
      return;
    }
    if (searchQuery === "slow") {
      sendJsonAfter(response, 200, {
        items: [{
          id: 7,
          title: "Slow search result",
          url: "https://example.com/slow",
          feed: { id: 1, title: "Fixture feed" },
          category: null,
          published_at: "2026-07-21T00:00:00Z",
          content_quality: "full",
          summary_zh: "慢搜索结果。",
          score: null,
          state: { status: "unread", saved: false, project: false, read_progress: 0 },
        }],
        next_cursor: null,
        has_more: false,
      }, 350);
      return;
    }
    if (searchQuery === "fast" || searchQuery === "partial") {
      sendJson(response, 200, {
        items: [{
          id: 9,
          title: searchQuery === "fast" ? "Fast search result" : "Partial search result",
          url: "https://example.com/search",
          feed: { id: 1, title: "Fixture feed" },
          category: null,
          published_at: "2026-07-19T00:00:00Z",
          content_quality: "full",
          summary_zh: "搜索测试文章。",
          score: null,
          state: { status: "unread", saved: false, project: false, read_progress: 0 },
        }],
        next_cursor: null,
        has_more: false,
      });
      return;
    }
    if (url.searchParams.get("module") === "read-later") {
      sendJson(response, 200, {
        items: [{
          id: 10,
          title: "Unsaved in-progress article",
          url: "https://example.com/in-progress",
          feed: { id: 1, title: "Fixture feed" },
          category: null,
          published_at: "2026-07-22T00:00:00Z",
          content_quality: "full",
          summary_zh: "真实进度测试文章。",
          score: null,
          state: { status: "unread", saved: false, project: false, read_progress: 0.4 },
        }],
        next_cursor: null,
        has_more: false,
      });
      return;
    }
    if (url.searchParams.get("cursor") === "cursor-page-2") {
      sendJson(response, 200, {
        items: [
          {
            id: 9,
            title: "Cursor article two",
            url: "https://example.com/two",
            feed: { id: 1, title: "Fixture feed" },
            category: null,
            published_at: "2026-07-19T00:00:00Z",
            content_quality: "full",
            summary_zh: "第二页测试文章。",
            score: null,
            state: { status: "unread", saved: false, project: false, read_progress: 0 },
          },
        ],
        next_cursor: null,
        has_more: false,
      });
      return;
    }
    sendJson(response, 200, {
      items: [
        {
          id: 7,
          title: "Keyboard article one",
          url: "https://example.com/one",
          feed: { id: 1, title: "Fixture feed" },
          category: null,
          published_at: "2026-07-21T00:00:00Z",
          content_quality: "full",
          summary_zh: "第一篇测试文章。",
          score: null,
          state: { status: "unread", saved: false, project: false, read_progress: 0 },
        },
        {
          id: 8,
          title: "Keyboard article two",
          url: "https://example.com/two",
          feed: { id: 1, title: "Fixture feed" },
          category: null,
          published_at: "2026-07-20T00:00:00Z",
          content_quality: "full",
          summary_zh: "第二篇测试文章。",
          score: null,
          state: { status: "unread", saved: false, project: false, read_progress: 0 },
        },
      ],
      next_cursor: "cursor-page-2",
      has_more: true,
    });
    return;
  }
  if (url.pathname === "/api/annotations/search" && request.method === "GET") {
    const searchQuery = url.searchParams.get("q");
    if (searchQuery === "partial") {
      sendJson(response, 500, { error: { message: "annotation fixture failure" } });
      return;
    }
    const items = searchQuery === "fast"
      ? [{ id: 2, article_id: 9, content: "Fast annotation", selected_text: null, article_title: "Fast search result" }]
      : searchQuery === "slow"
        ? [{ id: 1, article_id: 7, content: "Slow annotation", selected_text: null, article_title: "Slow search result" }]
        : searchQuery === "annotations-only"
          ? [{ id: 3, article_id: 7, content: "Annotation-only result", selected_text: null, article_title: "Annotation-only article" }]
          : [];
    if (searchQuery === "slow") {
      sendJsonAfter(response, 200, { items }, 350);
    } else {
      sendJson(response, 200, { items });
    }
    return;
  }
  if (url.pathname === "/api/articles/stats" && request.method === "GET") {
    const unscored = adminSyncCompleted ? 3 : 2;
    sendJson(response, 200, { total: unscored, scored: 0, unscored });
    return;
  }
  if (url.pathname === "/api/admin/usage/today" && request.method === "GET") {
    if (usageFailuresRemaining > 0) {
      usageFailuresRemaining -= 1;
      sendJson(response, 500, { error: { message: "usage fixture failure" } });
      return;
    }
    sendJson(response, 200, {
      day: "2026-07-22",
      scores: { count_today: 0, accounting: "database" },
      accounts: {
        score: { used: 0, limit: 60, remaining: 60 },
        ask: { used: 0, limit: 20, remaining: 20 },
        agent: { used: 0, limit: 20, remaining: 20 },
      },
      cost_ledger: { accounting: "fixture" },
    });
    return;
  }
  if (url.pathname === "/api/admin/pipeline-health" && request.method === "GET") {
    sendJson(response, 200, {
      status: "healthy",
      scheduler_enabled: true,
      queue: { queued: adminSyncCompleted ? 0 : 1, running: 0, failed_24h: 0, stale_running: 0 },
      jobs: [],
    });
    return;
  }
  if (url.pathname === "/api/admin/sync" && request.method === "POST") {
    adminSyncCompleted = true;
    sendJson(response, 200, { job_id: 89, job_type: "sync_miniflux_entries", status: "queued" });
    return;
  }
  if (url.pathname === "/api/recommendations/latest" && request.method === "GET") {
    sendJson(response, 200, { items: [], generated_at: "2026-07-21T00:00:00Z" });
    return;
  }
  if ((url.pathname === "/api/articles/7" || url.pathname === "/api/articles/9") && request.method === "GET") {
    const id = url.pathname.endsWith("/9") ? 9 : 7;
    sendJson(response, 200, { id, owner: currentUser.id, content_html: `<p>${currentUser.id}</p>` });
    return;
  }
  if (url.pathname === "/api/research/jobs" && request.method === "POST") {
    sendJson(response, 200, { job_id: completedResearchJob.id, poll_url: `/api/jobs/${completedResearchJob.id}` });
    return;
  }
  if (url.pathname === `/api/jobs/${completedResearchJob.id}` && request.method === "GET") {
    sendJson(response, 200, completedResearchJob);
    return;
  }
  if (url.pathname === "/api/jobs/89" && request.method === "GET") {
    sendJson(response, 200, {
      id: 89,
      job_type: "sync_miniflux_entries",
      status: "succeeded",
      progress: { completed: 1, total: 1 },
      result: { synced: 1 },
      last_error: null,
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:01:00Z",
      completed_at: "2026-07-22T00:01:00Z",
    });
    return;
  }
  if (url.pathname === "/api/jobs/7" && request.method === "GET") {
    jobRequestCount += 1;
    sendJson(response, 200, { status: jobRequestCount === 1 ? "queued" : "succeeded" });
    return;
  }

  proxyToApp(request, response);
});

function close() {
  proxy.close();
  app.kill("SIGTERM");
}

process.once("SIGINT", close);
process.once("SIGTERM", close);
app.once("exit", (code) => {
  if (code !== 0) process.exitCode = code ?? 1;
  proxy.close();
});

proxy.listen(proxyPort, "127.0.0.1");
