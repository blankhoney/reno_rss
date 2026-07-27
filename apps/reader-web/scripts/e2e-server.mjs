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
let dailyClusterFailuresRemaining = 0;
let articleAskFailuresRemaining = 0;
let articleStateFailuresRemaining = 0;
let researchFailuresRemaining = 0;
let annotationFailuresRemaining = 0;
let articleListFailuresRemaining = 0;
let adminSyncCompleted = false;
const articleStates = new Map();
const userAnnotations = new Map();
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

function sendSse(response, frames) {
  response.writeHead(200, {
    "cache-control": "no-cache, no-transform",
    "content-type": "text/event-stream",
  });
  response.end(frames.join(""));
}

function fixtureMode(request) {
  const referer = request.headers.referer;
  if (typeof referer !== "string") return null;
  try {
    return new URL(referer).searchParams.get("fixture");
  } catch {
    return null;
  }
}

function resetFixtures() {
  currentUser = users.ada;
  jobRequestCount = 0;
  usageFailuresRemaining = 0;
  dailyClusterFailuresRemaining = 0;
  articleAskFailuresRemaining = 0;
  articleStateFailuresRemaining = 0;
  researchFailuresRemaining = 0;
  annotationFailuresRemaining = 0;
  articleListFailuresRemaining = 0;
  adminSyncCompleted = false;
  articleStates.clear();
  userAnnotations.clear();
}

function articleStateFor(id) {
  return articleStates.get(id) ?? { status: "unread", saved: false, project: false, read_progress: 0.25 };
}

function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
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

const proxy = createServer(async (request, response) => {
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
  if (url.pathname === "/__e2e/daily/clusters-fail-once" && request.method === "POST") {
    dailyClusterFailuresRemaining = 1;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/__e2e/article-ask/fail-once" && request.method === "POST") {
    articleAskFailuresRemaining = 1;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/__e2e/article-state/fail-once" && request.method === "POST") {
    articleStateFailuresRemaining = 1;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/__e2e/research/fail-once" && request.method === "POST") {
    researchFailuresRemaining = 1;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/__e2e/annotation/fail-once" && request.method === "POST") {
    annotationFailuresRemaining = 1;
    sendJson(response, 200, { ok: true });
    return;
  }
  if (url.pathname === "/__e2e/article-list/fail-once" && request.method === "POST") {
    articleListFailuresRemaining = 1;
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
    if (articleListFailuresRemaining > 0) {
      articleListFailuresRemaining -= 1;
      sendJson(response, 503, { error: { code: "list_unavailable", message: "文章列表暂不可用，请重试。" } });
      return;
    }
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
  if (url.pathname === "/api/briefs/latest" && request.method === "GET") {
    if (fixtureMode(request) === "daily-error") {
      sendJson(response, 500, { error: { message: "brief fixture failure" } });
      return;
    }
    sendJson(response, 200, {
      brief: {
        generated_at: "2026-07-26T08:00:00Z",
        title: "今日研究简报",
        source: "fixture",
        must_read: [{
          article_id: 7,
          title: "Durable research workflows",
          rank: 1,
          tier: "must_read",
          rank_score: 91,
          reason: "可恢复证据链直接影响研究可信度。",
          summary_zh: "让浏览、标注与研究任务在导航后保持连续。",
          overall_score: 91,
        }],
        worth_scan: [{
          article_id: 8,
          title: "Keyboard article two",
          rank: 2,
          tier: "worth_scan",
          rank_score: 76,
          reason: "补充键盘工作流证据。",
          summary_zh: "验证原生控件与快捷键边界。",
          overall_score: 76,
        }],
        can_skip: [],
      },
    });
    return;
  }
  if (url.pathname === "/api/annotations/review" && request.method === "GET") {
    if (fixtureMode(request) === "daily-error") {
      sendJson(response, 500, { error: { message: "review fixture failure" } });
      return;
    }
    sendJson(response, 200, {
      items: [{
        id: 41,
        article_id: 7,
        type: "annotation",
        selected_text: "A durable note returns when it matters.",
        content: "A durable note returns when it matters.",
        color: "yellow",
        tags: ["evidence"],
        created_at: "2026-07-24T08:00:00Z",
        next_review_at: "2026-07-26T08:00:00Z",
        interval_days: 3,
        review_count: 1,
        article_title: "Durable research workflows",
        article_url: "https://example.com/durable-research",
      }],
    });
    return;
  }
  if (url.pathname === "/api/clusters/latest" && request.method === "GET") {
    if (dailyClusterFailuresRemaining > 0) {
      dailyClusterFailuresRemaining -= 1;
      sendJson(response, 500, { error: { message: "cluster fixture failure" } });
      return;
    }
    if (fixtureMode(request) === "daily-error") {
      sendJson(response, 500, { error: { message: "cluster fixture failure" } });
      return;
    }
    sendJson(response, 200, {
      clusters: [{
        id: "durable-research",
        label: "可恢复研究工作流",
        main_article_id: 7,
        related_article_ids: [8],
        size: 2,
      }],
    });
    return;
  }
  if (url.pathname === "/api/themes/latest" && request.method === "GET") {
    if (fixtureMode(request) === "daily-error") {
      sendJson(response, 500, { error: { message: "theme fixture failure" } });
      return;
    }
    sendJson(response, 200, {
      themes: [{
        label: "Evidence continuity",
        weight: 8.7,
        article_ids: [7, 8],
      }],
    });
    return;
  }
  if (url.pathname === "/api/feeds" && request.method === "GET") {
    if (fixtureMode(request) === "daily-error") {
      sendJson(response, 500, { error: { message: "feed fixture failure" } });
      return;
    }
    sendJson(response, 200, {
      items: [
        {
          id: 1,
          title: "Fixture Research",
          status: "active",
          hidden: false,
          quality_score: 92,
          user_priority: 1,
          article_count: 12,
        },
        {
          id: 2,
          title: "Low-signal Fixture",
          status: "active",
          hidden: false,
          quality_score: 42,
          user_priority: -1,
          article_count: 3,
        },
      ],
    });
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
  if (url.pathname === "/api/articles/7/ask" && request.method === "POST") {
    if (articleAskFailuresRemaining > 0) {
      articleAskFailuresRemaining -= 1;
      sendJson(response, 503, {
        error: { code: "ask_unavailable", message: "文章助手暂不可用，请重试。" },
      });
      return;
    }
    sendSse(response, [
      "data: E2E grounded answer.\n\n",
      "event: citations\ndata: {\"citations\":[{\"quote\":\"Evidence should survive navigation.\",\"start_hint\":0}]}\n\n",
      "event: done\ndata: {}\n\n",
    ]);
    return;
  }
  if ((url.pathname === "/api/articles/7/state" || url.pathname === "/api/articles/9/state") && request.method === "POST") {
    if (articleStateFailuresRemaining > 0) {
      articleStateFailuresRemaining -= 1;
      sendJson(response, 503, { error: { code: "state_unavailable", message: "状态更新暂不可用，请重试。" } });
      return;
    }
    const id = url.pathname.includes("/9/") ? 9 : 7;
    const payload = await readJsonBody(request);
    const state = { ...articleStateFor(id) };
    if (typeof payload.status === "string") state.status = payload.status;
    if (typeof payload.saved === "boolean") state.saved = payload.saved;
    if (typeof payload.project === "boolean") state.project = payload.project;
    if (typeof payload.read_progress === "number") state.read_progress = payload.read_progress;
    articleStates.set(id, state);
    sendJson(response, 200, {
      state,
    });
    return;
  }
  if ((url.pathname === "/api/articles/7/annotations" || url.pathname === "/api/articles/9/annotations") && request.method === "GET") {
    const articleId = url.pathname.includes("/9/") ? 9 : 7;
    const mode = fixtureMode(request);
    if (articleId === 7 && mode === "annotation-inline-markup") {
      sendJson(response, 200, {
        items: [{
          id: 53,
          article_id: 7,
          type: "annotation",
          selected_text: "Structured evidence",
          content: "Keep the structured evidence note.",
          color: "green",
          tags: ["evidence"],
          anchor: {
            kind: "text-quote",
            version: 1,
            exact: "Structured evidence",
            prefix: "Intro: ",
            suffix: " survives refresh.",
            start: 7,
            end: 26,
          },
          created_at: "2026-07-24T08:00:00Z",
          next_review_at: null,
          interval_days: 3,
          review_count: 1,
        }],
      });
      return;
    }
    if (articleId === 7 && mode === "annotation-repeated") {
      sendJson(response, 200, {
        items: [{
          id: 51,
          article_id: 7,
          type: "annotation",
          selected_text: "Repeated evidence.",
          content: "Keep the intended repeated evidence.",
          color: "blue",
          tags: ["evidence"],
          anchor: {
            kind: "text-quote",
            version: 1,
            exact: "Repeated evidence.",
            prefix: "First context: Repeated evidence.Intended context: ",
            suffix: " Closing context.",
            start: 51,
            end: 69,
          },
          created_at: "2026-07-24T08:00:00Z",
          next_review_at: null,
          interval_days: 3,
          review_count: 1,
        }],
      });
      return;
    }
    if (articleId === 7 && mode === "annotation-ambiguous") {
      sendJson(response, 200, {
        items: [{
          id: 52,
          article_id: 7,
          type: "annotation",
          selected_text: "Repeated evidence.",
          content: "Do not silently bind this note.",
          color: "yellow",
          tags: ["evidence"],
          anchor: {
            kind: "text-quote",
            version: 1,
            exact: "Repeated evidence.",
            prefix: "same context: ",
            suffix: ".",
            start: 14,
            end: 32,
          },
          created_at: "2026-07-24T08:00:00Z",
          next_review_at: null,
          interval_days: 3,
          review_count: 1,
        }],
      });
      return;
    }
    const fixtureItems = articleId === 7
      ? [{
          id: 41,
          article_id: 7,
          type: "annotation",
          selected_text: "A durable note returns when it matters.",
          content: "Keep evidence attached to its source.",
          color: "yellow",
          tags: ["evidence"],
          created_at: "2026-07-24T08:00:00Z",
          next_review_at: "2026-07-26T08:00:00Z",
          interval_days: 3,
          review_count: 1,
        }]
      : [];
    const userItems = userAnnotations.get(`${currentUser.id}:${articleId}`) ?? [];
    sendJson(response, 200, { items: [...userItems, ...fixtureItems] });
    return;
  }
  if ((url.pathname === "/api/articles/7/annotations" || url.pathname === "/api/articles/9/annotations") && request.method === "POST") {
    if (annotationFailuresRemaining > 0) {
      annotationFailuresRemaining -= 1;
      sendJson(response, 503, { error: { code: "annotation_unavailable", message: "标注保存暂不可用，请重试。" } });
      return;
    }
    const articleId = url.pathname.includes("/9/") ? 9 : 7;
    const payload = await readJsonBody(request);
    const key = `${currentUser.id}:${articleId}`;
    const existing = userAnnotations.get(key) ?? [];
    const annotation = {
      id: 60 + existing.length,
      article_id: articleId,
      type: payload.type ?? "annotation",
      selected_text: payload.selected_text ?? null,
      content: payload.content ?? "",
      color: payload.color ?? "yellow",
      tags: payload.tags ?? [],
      anchor: payload.anchor ?? null,
      created_at: "2026-07-27T00:00:00Z",
      next_review_at: null,
      interval_days: 1,
      review_count: 0,
    };
    existing.push(annotation);
    userAnnotations.set(key, existing);
    sendJson(response, 201, { annotation });
    return;
  }
  if ((url.pathname === "/api/articles/7" || url.pathname === "/api/articles/9") && request.method === "GET") {
    const id = url.pathname.endsWith("/9") ? 9 : 7;
    const mode = fixtureMode(request);
    const repeatedAnnotationFixture = id === 7 && mode === "annotation-repeated";
    const ambiguousAnnotationFixture = id === 7 && mode === "annotation-ambiguous";
    const inlineMarkupAnnotationFixture = id === 7 && mode === "annotation-inline-markup";
    const contentHtml = repeatedAnnotationFixture
      ? "<p>New preface. First context: Repeated evidence.</p><p>Intended context: Repeated evidence. Closing context.</p>"
      : ambiguousAnnotationFixture
        ? "<p>same context: Repeated evidence. same context: Repeated evidence.</p>"
        : inlineMarkupAnnotationFixture
          ? "<p>Intro: Structured <em>evidence</em> survives refresh.</p>"
          : "<p>Evidence persists.</p><p>Evidence should survive navigation.</p><p>A durable note returns when it matters.</p>";
    const contentText = repeatedAnnotationFixture
      ? "New preface. First context: Repeated evidence.Intended context: Repeated evidence. Closing context."
      : ambiguousAnnotationFixture
        ? "same context: Repeated evidence. same context: Repeated evidence."
        : inlineMarkupAnnotationFixture
          ? "Intro: Structured evidence survives refresh."
          : "Evidence persists. Evidence should survive navigation. A durable note returns when it matters.";
    sendJson(response, 200, {
      id,
      owner: currentUser.id,
      title: id === 7 ? "Durable research workflows" : "Fast search result",
      url: id === 7 ? "https://example.com/durable-research" : "https://example.com/search",
      feed: { id: 1, title: "Fixture Research" },
      category: { id: 2, title: "Research systems" },
      published_at: "2026-07-24T08:00:00Z",
      content_quality: "full",
      content_html: contentHtml,
      content_zh: null,
      content_zh_status: "none",
      translated_at: null,
      content_text: contentText,
      content_source: "fixture",
      summary_zh: "让浏览、标注与研究任务在导航后保持连续。",
      summary_original: "Keep the evidence chain durable.",
      source_language: "en",
      score: null,
      state: articleStateFor(id),
      sources: [],
    });
    return;
  }
  if (url.pathname === "/api/research/jobs" && request.method === "POST") {
    if (researchFailuresRemaining > 0) {
      researchFailuresRemaining -= 1;
      sendJson(response, 200, { job_id: 90, poll_url: "/api/jobs/90" });
      return;
    }
    sendJson(response, 200, { job_id: completedResearchJob.id, poll_url: `/api/jobs/${completedResearchJob.id}` });
    return;
  }
  if (url.pathname === "/api/jobs/90" && request.method === "GET") {
    sendJson(response, 200, {
      id: 90,
      job_type: "research",
      status: "failed",
      progress: { completed: 0, total: 1 },
      result: null,
      last_error: "研究 provider 超时，请重试",
      created_at: "2026-07-22T00:00:00Z",
      updated_at: "2026-07-22T00:01:00Z",
      completed_at: "2026-07-22T00:01:00Z",
    });
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
