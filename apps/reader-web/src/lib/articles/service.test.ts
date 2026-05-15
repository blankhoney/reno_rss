import assert from "node:assert/strict";
import test from "node:test";
import type { Article } from "./types";
import { assessArticleContent, decideFetchedArticleContent } from "./contentQuality";
import {
  filterArticlesForModule,
  articleNeedsOriginalContentFetch,
  minifluxEntryFilterForModule,
  MODULE_IDS,
  resolveArticlesListModuleId,
  resolveArticleSortId,
  sanitizeArticleHtml,
  classifyArticleContentStatus,
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
    contentStatus: input.contentStatus ?? "partial",
    contentIssue: input.contentIssue ?? "rss_fragment",
    contentFetchAttempted: input.contentFetchAttempted ?? false,
    summaryZh: input.summaryZh ?? "",
    summaryOriginal: input.summaryOriginal ?? "",
    sourceLanguage: input.sourceLanguage ?? "unknown",
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
      summaryZh: "",
      summaryOriginal: "",
      sourceLanguage: "unknown",
      dimensionReasons: {},
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
  assert.deepEqual(minifluxEntryFilterForModule("project", 25), {
    status: "all",
    starred: undefined,
    limit: 25,
  });
});

test("resolveArticleSortId defaults and rejects unknown explicit values", () => {
  assert.deepEqual(resolveArticleSortId(false, null), { ok: true, sortId: "default" });
  assert.deepEqual(resolveArticleSortId(true, "latest"), { ok: true, sortId: "latest" });
  assert.deepEqual(resolveArticleSortId(true, "technical"), { ok: true, sortId: "technical" });
  assert.deepEqual(resolveArticleSortId(true, "unknown"), { ok: false });
});

test("project module keeps queue order", () => {
  const sorted = sortArticlesForModule(
    [article(1, { overall: 10 }), article(2, { overall: 90 })],
    "project",
  );
  assert.deepEqual(sorted.map((item) => item.id), [1, 2]);
});

test("explicit score sorting puts unscored articles last", () => {
  const sorted = sortArticlesForModule(
    [article(1, { score: null }), article(2, { overall: 60 }), article(3, { overall: 90 })],
    "all",
    "score",
  );

  assert.deepEqual(sorted.map((item) => item.id), [3, 2, 1]);
});

test("explicit dimension sorting uses the selected dimension", () => {
  const sorted = sortArticlesForModule(
    [
      article(1, {
        score: {
          overall: 95,
          dimensions: {
            importance: 90,
            usefulness: 90,
            timeliness: 90,
            depth: 90,
            technical_value: 10,
            business_value: 90,
            trend_value: 90,
          },
          tags: [],
          reason: "",
          summaryZh: "",
          summaryOriginal: "",
          sourceLanguage: "unknown",
          dimensionReasons: {},
          scoredAt: null,
        },
      }),
      article(2, {
        score: {
          overall: 50,
          dimensions: {
            importance: 50,
            usefulness: 50,
            timeliness: 50,
            depth: 50,
            technical_value: 99,
            business_value: 20,
            trend_value: 20,
          },
          tags: [],
          reason: "",
          summaryZh: "",
          summaryOriginal: "",
          sourceLanguage: "unknown",
          dimensionReasons: {},
          scoredAt: null,
        },
      }),
    ],
    "all",
    "technical",
  );

  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
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

test("sanitizeArticleHtml discards xmp raw text content", () => {
  const html = sanitizeArticleHtml(
    '<p>Before</p><xmp><script>alert(1)</script><img src="x" onerror="alert(2)"></xmp><p>After</p>',
  );

  assert.equal(html.includes("<xmp"), false);
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes("onerror"), false);
  assert.equal(html.includes("<img"), false);
  assert.match(html, /Before/);
  assert.match(html, /After/);
});

test("sanitizeArticleHtml makes http links open safely in a new tab", () => {
  const html = sanitizeArticleHtml(
    '<p><a href="https://example.com/path?q=1">Source</a> <a href="mailto:test@example.com">Mail</a></p>',
  );

  assert.match(html, /<a href="https:\/\/example.com\/path\?q=1" target="_blank" rel="noreferrer noopener">Source<\/a>/);
  assert.match(html, /<a href="mailto:test@example.com">Mail<\/a>/);
});

test("articleNeedsOriginalContentFetch detects empty, short, and Comments placeholders", () => {
  assert.equal(articleNeedsOriginalContentFetch(""), true);
  assert.equal(articleNeedsOriginalContentFetch("<p>Comments</p>"), true);
  assert.equal(articleNeedsOriginalContentFetch("<p>Short teaser.</p>"), true);
  assert.equal(articleNeedsOriginalContentFetch(`<p>${"full body ".repeat(80)}</p>`), false);
});

test("classifyArticleContentStatus marks short or placeholder content as partial", () => {
  assert.equal(classifyArticleContentStatus("<p>Comments</p>"), "partial");
  assert.equal(classifyArticleContentStatus("<p>Short teaser.</p>"), "partial");
  assert.equal(classifyArticleContentStatus(`<p>${"full body ".repeat(80)}</p>`), "full");
});

test("assessArticleContent detects source error pages and login walls", () => {
  assert.deepEqual(assessArticleContent("<p>Comments</p>").issue, "rss_fragment");
  assert.deepEqual(
    assessArticleContent("<p>Something went wrong, but don’t fret — let’s give it another shot. Try again.</p>").issue,
    "blocked_or_error_page",
  );
  assert.deepEqual(
    assessArticleContent("<p>Please enable JavaScript and cookies to continue. Access denied.</p>").issue,
    "blocked_or_error_page",
  );
  assert.deepEqual(
    assessArticleContent(`<p>Just a moment. ${"checking browser ".repeat(180)}</p>`).issue,
    "blocked_or_error_page",
  );
});

test("decideFetchedArticleContent applies useful content and rejects blocked pages", () => {
  const current = "<p>Comments</p>";
  const full = `<p>${"full article body ".repeat(90)}</p>`;
  const applied = decideFetchedArticleContent(current, full);
  assert.equal(applied.html, full);
  assert.deepEqual(applied.fetchResult.outcome, "applied");
  assert.deepEqual(applied.fetchResult.outcome === "applied" ? applied.fetchResult.quality : null, "full");

  const blocked = decideFetchedArticleContent(
    current,
    "<p>Something went wrong. Try again. Privacy related extensions may cause issues.</p>",
  );
  assert.equal(blocked.html, current);
  assert.equal(blocked.fetchResult.outcome, "rejected");
  assert.equal(blocked.fetchResult.outcome === "rejected" ? blocked.fetchResult.reason : null, "blocked_or_error_page");
  assert.equal(blocked.fetchResult.issue, "blocked_or_error_page");
  assert.ok(blocked.fetchResult.textLength > 0);

  const unchanged = decideFetchedArticleContent("<p>Short body</p>", "<p>Short body</p>");
  assert.equal(unchanged.html, "<p>Short body</p>");
  assert.equal(unchanged.fetchResult.outcome, "unchanged");
});
