import assert from "node:assert/strict";
import test from "node:test";
import type { Article } from "./types";
import {
  filterArticlesForModule,
  minifluxEntryFilterForModule,
  MODULE_IDS,
  resolveArticlesListModuleId,
  sanitizeArticleHtml,
  sortArticlesForModule,
} from "./service";

test("resolveArticlesListModuleId defaults when module param absent", () => {
  assert.deepEqual(resolveArticlesListModuleId(false, null), { ok: true, moduleId: "all" });
});

test("resolveArticlesListModuleId accepts every MODULE_IDS value when present", () => {
  for (const moduleId of MODULE_IDS) {
    assert.deepEqual(resolveArticlesListModuleId(true, moduleId), { ok: true, moduleId });
  }
});

test("resolveArticlesListModuleId rejects empty or unknown module", () => {
  assert.deepEqual(resolveArticlesListModuleId(true, ""), { ok: false });
  assert.deepEqual(resolveArticlesListModuleId(true, "nope"), { ok: false });
  assert.deepEqual(resolveArticlesListModuleId(true, "overall"), { ok: false });
});

function article(
  id: number,
  input: Partial<Article> & { overall?: number } = {},
): Article {
  const overall = input.overall ?? 50;
  return {
    id,
    userId: input.userId ?? 7,
    feedId: input.feedId ?? 1,
    feedTitle: input.feedTitle ?? "Feed",
    categoryId: input.categoryId ?? 1,
    categoryTitle: input.categoryTitle ?? "AI",
    title: input.title ?? `Article ${id}`,
    url: input.url ?? "https://example.com",
    contentHtml: input.contentHtml ?? "<p>Body</p>",
    status: input.status ?? "unread",
    starred: input.starred ?? false,
    publishedAt: input.publishedAt ?? "2026-05-13T00:00:00.000Z",
    score: input.score ?? {
      overall,
      dimensions: {
        importance: overall,
        usefulness: overall,
        timeliness: overall,
        depth: overall,
        technical_value: overall,
        business_value: overall,
        trend_value: overall,
      },
      tags: [],
      reason: "",
      scoredAt: null,
    },
    readLater: input.readLater ?? false,
    lastReadAt: input.lastReadAt ?? null,
  };
}

test("minifluxEntryFilterForModule fetches all statuses for latest and scored modules", () => {
  assert.deepEqual(minifluxEntryFilterForModule("all", 25), {
    status: "all",
    starred: undefined,
    limit: 25,
  });
  assert.deepEqual(minifluxEntryFilterForModule("technical", 25), {
    status: "all",
    starred: undefined,
    limit: 25,
  });
  assert.deepEqual(minifluxEntryFilterForModule("starred", 25), {
    status: "all",
    starred: true,
    limit: 25,
  });
  assert.deepEqual(minifluxEntryFilterForModule("read-later", 25), {
    status: "all",
    starred: undefined,
    limit: 25,
  });
});

test("filterArticlesForModule keeps only read-later items for read-later module", () => {
  const filtered = filterArticlesForModule(
    [article(1, { readLater: false }), article(2, { readLater: true })],
    "read-later",
  );
  assert.deepEqual(filtered.map((item) => item.id), [2]);
});

test("read module sorts by most recent lastReadAt", () => {
  const sorted = sortArticlesForModule(
    [
      article(1, { status: "read", lastReadAt: "2026-05-12T00:00:00.000Z" }),
      article(2, { status: "read", lastReadAt: "2026-05-13T00:00:00.000Z" }),
    ],
    "read",
  );
  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
});

test("all module sorts by most recent publishedAt", () => {
  const sorted = sortArticlesForModule(
    [
      article(1, { publishedAt: "2026-05-12T00:00:00.000Z" }),
      article(2, { publishedAt: "2026-05-13T00:00:00.000Z" }),
    ],
    "all",
  );
  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
});

test("sanitizeArticleHtml removes script tags and inline event handlers", () => {
  const html = sanitizeArticleHtml('<p onclick="bad()">Hi</p><script>alert(1)</script>');
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes("onclick"), false);
  assert.match(html, /Hi/);
});
