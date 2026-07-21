/* AI Reader PWA service worker.
 *
 * Offline support caches only approved shell/static assets and exact article-detail
 * JSON. Article HTML is always sanitized by sanitizeArticleHtml() after the
 * client maps cached JSON into its render model; this worker never renders HTML.
 */
const CACHE_PREFIX = "ai-reader-";
const SHELL_CACHE = `${CACHE_PREFIX}shell-v2`;
const ARTICLE_DETAIL_CACHE = `${CACHE_PREFIX}article-details-v2`;
const OWNED_CACHES = new Set([SHELL_CACHE, ARTICLE_DETAIL_CACHE]);
const SHELL_URLS = ["/", "/manifest.webmanifest", "/brand/ai-reader-icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_URLS))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) => Promise.all(names.filter(isObsoleteOwnedCache).map((name) => caches.delete(name))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (isOfflineArticleDetailRequest(request, url)) {
    event.respondWith(networkFirstArticleDetail(request, event));
    return;
  }

  if (isShellStaticRequest(url)) {
    event.respondWith(cacheFirstShellAsset(request, event));
  }
});

function isObsoleteOwnedCache(name) {
  return name.startsWith(CACHE_PREFIX) && !OWNED_CACHES.has(name);
}

function isOfflineArticleDetailRequest(request, url) {
  return request.method === "GET" && /^\/api\/articles\/[1-9]\d*$/.test(url.pathname);
}

function isShellStaticRequest(url) {
  return SHELL_URLS.includes(url.pathname) || url.pathname.startsWith("/_next/static/");
}

function isSuccessfulJson(response) {
  const contentType = response.headers.get("content-type") || "";
  return response.ok && /\bapplication\/(?:[\w.+-]+\+)?json\b/i.test(contentType);
}

async function networkFirstArticleDetail(request, event) {
  const cache = await caches.open(ARTICLE_DETAIL_CACHE);
  try {
    const response = await fetch(request);
    if (isSuccessfulJson(response)) {
      event.waitUntil(cache.put(request, response.clone()));
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: { code: "offline", message: "offline" } }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }
}

async function cacheFirstShellAsset(request, event) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok) {
    event.waitUntil(cache.put(request, response.clone()));
  }
  return response;
}
