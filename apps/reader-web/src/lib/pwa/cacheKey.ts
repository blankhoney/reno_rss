/**
 * Stable cache keys for the PWA service worker article API cache.
 * Kept in sync with apps/reader-web/public/sw.js (apiCacheKey / isArticlesApiGet).
 *
 * Offline only caches API JSON. Article HTML must still pass sanitizeArticleHtml
 * on render (client path) — the SW does not trust or render HTML.
 */

export function isArticlesApiPath(pathname: string): boolean {
  return pathname === "/api/articles" || pathname.startsWith("/api/articles/");
}

export function articlesApiCacheKey(method: string, url: string | URL): string {
  const parsed = typeof url === "string" ? new URL(url, "https://ai-reader.local") : url;
  return `${method.toUpperCase()}:${parsed.pathname}${parsed.search}`;
}
