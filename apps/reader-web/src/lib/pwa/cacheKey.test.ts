import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

import { isOfflineArticleDetailPath } from "./cacheKey.ts";

type FetchHandler = (event: {
  request: Request;
  respondWith: (response: Promise<Response> | Response) => void;
  waitUntil: (work: Promise<unknown>) => void;
}) => void;

type LifecycleHandler = (event: { waitUntil: (work: Promise<unknown>) => void }) => void;

class MemoryCache {
  readonly entries = new Map<string, Response>();

  async addAll(urls: string[]): Promise<void> {
    for (const url of urls) {
      this.entries.set(new URL(url, "http://127.0.0.1:3010").href, new Response("shell"));
    }
  }

  async put(request: Request, response: Response): Promise<void> {
    this.entries.set(request.url, response);
  }

  async match(request: Request | string): Promise<Response | undefined> {
    const url = typeof request === "string" ? new URL(request, "http://127.0.0.1:3010").href : request.url;
    return this.entries.get(url)?.clone();
  }
}

class MemoryCacheStorage {
  readonly stores = new Map<string, MemoryCache>();

  async open(name: string): Promise<MemoryCache> {
    let cache = this.stores.get(name);
    if (cache == null) {
      cache = new MemoryCache();
      this.stores.set(name, cache);
    }
    return cache;
  }

  async keys(): Promise<string[]> {
    return [...this.stores.keys()];
  }

  async delete(name: string): Promise<boolean> {
    return this.stores.delete(name);
  }
}

function loadWorker(fetchImpl: (request: Request) => Promise<Response>, caches = new MemoryCacheStorage()) {
  const handlers = new Map<string, FetchHandler | LifecycleHandler>();
  const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../../public/sw.js"), "utf8");
  const self = {
    location: { origin: "http://127.0.0.1:3010" },
    addEventListener(type: string, handler: FetchHandler | LifecycleHandler) {
      handlers.set(type, handler);
    },
    skipWaiting: async () => undefined,
    clients: { claim: async () => undefined },
  };

  vm.runInNewContext(source, {
    URL,
    Request,
    Response,
    JSON,
    Promise,
    caches,
    fetch: fetchImpl,
    self,
  });

  async function dispatchFetch(path: string): Promise<{ response: Response | null; waits: Promise<unknown>[] }> {
    const waits: Promise<unknown>[] = [];
    let response: Promise<Response> | null = null;
    const handler = handlers.get("fetch") as FetchHandler;
    handler({
      request: new Request(new URL(path, self.location.origin)),
      respondWith(value) {
        response = Promise.resolve(value);
      },
      waitUntil(work) {
        waits.push(work);
      },
    });
    return { response: response == null ? null : await response, waits };
  }

  async function dispatchLifecycle(type: "install" | "activate"): Promise<void> {
    const waits: Promise<unknown>[] = [];
    const handler = handlers.get(type) as LifecycleHandler;
    handler({ waitUntil: (work) => waits.push(work) });
    await Promise.all(waits);
  }

  return { caches, dispatchFetch, dispatchLifecycle };
}

test("isOfflineArticleDetailPath allows only exact positive-integer article detail paths", () => {
  assert.equal(isOfflineArticleDetailPath("/api/articles/12"), true);
  assert.equal(isOfflineArticleDetailPath("/api/articles"), false);
  assert.equal(isOfflineArticleDetailPath("/api/articles/12/annotations"), false);
  assert.equal(isOfflineArticleDetailPath("/api/articles/12/ask"), false);
  assert.equal(isOfflineArticleDetailPath("/api/articles/0"), false);
  assert.equal(isOfflineArticleDetailPath("/api/articles/01"), false);
  assert.equal(isOfflineArticleDetailPath("/api/auth/me"), false);
});

test("service worker leaves private and dynamic APIs to the network", async () => {
  let fetches = 0;
  const worker = loadWorker(async () => {
    fetches += 1;
    return new Response(JSON.stringify({ status: "running" }), {
      headers: { "content-type": "application/json" },
    });
  });

  for (const path of [
    "/api/auth/me",
    "/api/jobs/7",
    "/api/admin/users",
    "/api/articles?module=all",
    "/api/articles/7/annotations",
    "/api/annotations/search?q=private",
    "/api/export/project",
  ]) {
    const result = await worker.dispatchFetch(path);
    assert.equal(result.response, null, path);
  }
  assert.equal(fetches, 0);
});

test("service worker caches only successful JSON article details and falls back offline", async () => {
  let online = true;
  const worker = loadWorker(async (request) => {
    if (!online) throw new TypeError("offline");
    return new Response(JSON.stringify({ id: 7, content_html: "<p>safe path</p>" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });

  const onlineResult = await worker.dispatchFetch("/api/articles/7");
  assert.equal(onlineResult.response?.status, 200);
  await Promise.all(onlineResult.waits);

  online = false;
  const offlineResult = await worker.dispatchFetch("/api/articles/7");
  assert.equal(offlineResult.response?.status, 200);
  assert.deepEqual(await offlineResult.response?.json(), { id: 7, content_html: "<p>safe path</p>" });
});

test("service worker never caches failed or non-JSON article-detail responses", async () => {
  for (const response of [
    new Response("not found", { status: 404, headers: { "content-type": "text/plain" } }),
    new Response("broken", { status: 500, headers: { "content-type": "application/json" } }),
    new Response("html", { status: 200, headers: { "content-type": "text/html" } }),
  ]) {
    const worker = loadWorker(async () => response.clone());
    const result = await worker.dispatchFetch("/api/articles/7");
    await Promise.all(result.waits);
    const cacheNames = await worker.caches.keys();
    const cached = await Promise.all(
      cacheNames.map(async (name) => (await worker.caches.open(name)).match("/api/articles/7")),
    );
    assert.deepEqual(cached, cacheNames.map(() => undefined));
  }
});

test("service worker activation removes obsolete owned caches but keeps unrelated caches", async () => {
  const caches = new MemoryCacheStorage();
  await caches.open("ai-reader-shell-v1");
  await caches.open("ai-reader-api-v1");
  await caches.open("third-party-cache");
  const worker = loadWorker(async () => new Response("ok"), caches);

  await worker.dispatchLifecycle("activate");

  const names = await caches.keys();
  assert.equal(names.includes("ai-reader-shell-v1"), false);
  assert.equal(names.includes("ai-reader-api-v1"), false);
  assert.equal(names.includes("third-party-cache"), true);
});
