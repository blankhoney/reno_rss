import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { articlesApiCacheKey, isArticlesApiPath } from "./cacheKey.ts";

test("isArticlesApiPath matches list and detail routes only", () => {
  assert.equal(isArticlesApiPath("/api/articles"), true);
  assert.equal(isArticlesApiPath("/api/articles/12"), true);
  assert.equal(isArticlesApiPath("/api/articles/12/ask"), true);
  assert.equal(isArticlesApiPath("/api/recommendations/latest"), false);
  assert.equal(isArticlesApiPath("/api/auth/me"), false);
});

test("articlesApiCacheKey is stable across full URL and path+query", () => {
  assert.equal(
    articlesApiCacheKey("get", "https://example.com/api/articles?module=unread&q=ai"),
    "GET:/api/articles?module=unread&q=ai",
  );
  assert.equal(
    articlesApiCacheKey("GET", new URL("https://example.com/api/articles/9")),
    "GET:/api/articles/9",
  );
});

test("sw.js exists with sanitize invariant and revalidate / network-first strategy", () => {
  const root = join(dirname(fileURLToPath(import.meta.url)), "../../../public/sw.js");
  const source = readFileSync(root, "utf8");
  assert.match(source, /sanitizeArticleHtml/);
  assert.match(source, /network-first|networkFirstArticles/i);
  assert.match(source, /revalidate/i);
  assert.match(source, /\/api\/articles/);
  assert.match(source, /SHELL_CACHE|ai-reader-shell/);
});
