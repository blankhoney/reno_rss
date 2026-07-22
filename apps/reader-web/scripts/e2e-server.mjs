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
};

let currentUser = users.ada;
let jobRequestCount = 0;

function sendJson(response, status, payload) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

function resetFixtures() {
  currentUser = users.ada;
  jobRequestCount = 0;
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
  if (url.pathname === "/api/articles/stats" && request.method === "GET") {
    sendJson(response, 200, { total: 2, scored: 0, unscored: 2 });
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
