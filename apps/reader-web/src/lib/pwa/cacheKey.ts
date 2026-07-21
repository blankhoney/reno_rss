/**
 * Cache policy shared with the PWA service worker.
 *
 * Offline cache stores only article-detail JSON. The article adapter sanitizes
 * untrusted HTML every time it maps that JSON into the render model.
 */

export const PWA_CACHE_PREFIX = "ai-reader-";
export const ARTICLE_DETAIL_CACHE = `${PWA_CACHE_PREFIX}article-details-v2`;
export const PRIVATE_CACHE_OWNER_KEY = "ai-reader.pwa.article-cache-owner";

export function isOfflineArticleDetailPath(pathname: string): boolean {
  return /^\/api\/articles\/[1-9]\d*$/.test(pathname);
}

type CacheStorageLike = Pick<CacheStorage, "delete">;
type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

type PrivateCacheDependencies = {
  cacheStorage?: CacheStorageLike | null;
  storage?: StorageLike | null;
};

function browserCacheStorage(): CacheStorageLike | null {
  return "caches" in globalThis ? globalThis.caches : null;
}

function browserStorage(): StorageLike | null {
  return "localStorage" in globalThis ? globalThis.localStorage : null;
}

export async function clearPrivateArticleCache({
  cacheStorage = browserCacheStorage(),
  storage = browserStorage(),
}: PrivateCacheDependencies = {}): Promise<void> {
  await cacheStorage?.delete(ARTICLE_DETAIL_CACHE);
  storage?.removeItem(PRIVATE_CACHE_OWNER_KEY);
}

export async function synchronizePrivateArticleCacheOwner(
  userId: string,
  {
    cacheStorage = browserCacheStorage(),
    storage = browserStorage(),
  }: PrivateCacheDependencies = {},
): Promise<void> {
  if (cacheStorage == null || storage == null) return;

  if (storage.getItem(PRIVATE_CACHE_OWNER_KEY) === userId) return;

  await cacheStorage.delete(ARTICLE_DETAIL_CACHE);
  storage.setItem(PRIVATE_CACHE_OWNER_KEY, userId);
}
