/* AI Reader PWA service worker.
 * Offline strategy: network-first for /api/articles GET JSON (with revalidate cache write),
 * cache-first for app shell. Article HTML is NEVER rendered from cache without going through
 * sanitizeArticleHtml() in the React client — offline only stores API JSON payloads.
 */
const SHELL_CACHE = "ai-reader-shell-v1";
const API_CACHE = "ai-reader-api-v1";
const SHELL_URLS = ["/", "/manifest.webmanifest", "/brand/ai-reader-icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (url.pathname.startsWith("/api/articles")) {
    event.respondWith(networkFirstArticles(request));
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirstShell(request));
  }
});

/** network-first + revalidate cache for article API JSON */
async function networkFirstArticles(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const response = await fetch(request);
    if (response.ok) {
      // revalidate: store fresh JSON for offline reads
      cache.put(request, response.clone());
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

async function cacheFirstShell(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    const cache = await caches.open(SHELL_CACHE);
    cache.put(request, response.clone());
    return response;
  } catch {
    return (await caches.match("/")) || Response.error();
  }
}
