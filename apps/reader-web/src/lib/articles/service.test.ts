import assert from "node:assert/strict";
import test from "node:test";
import type { Article } from "./types";
import { assessArticleContent } from "./contentQuality";
import {
  filterArticlesForModule,
  filterHiddenFeedsForModule,
  articleNeedsOriginalContentFetch,
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
    feedHidden: input.feedHidden,
    feedQualityScore: input.feedQualityScore,
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
    project: input.project ?? false,
    publishedAt: input.publishedAt ?? "2026-05-13T00:00:00.000Z",
    score: input.score ?? {
      overall,
      dimensions: {
        topic_relevance: overall,
        information_density: overall,
        source_quality: overall,
        novelty: overall,
        timeliness: overall,
        actionability: overall,
        reading_cost_fit: overall,
        risk_uncertainty: 100 - overall,
      },
      tags: [],
      reason: "",
      summaryZh: "",
      summaryOriginal: "",
      sourceLanguage: "unknown",
      dimensionReasons: {},
      scoredAt: null,
    },
    myFeedback: input.myFeedback ?? null,
    readProgress: input.readProgress,
    readLater: input.readLater ?? false,
    lastReadAt: input.lastReadAt ?? null,
  };
}

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
            topic_relevance: 10,
            information_density: 90,
            source_quality: 90,
            novelty: 90,
            timeliness: 90,
            actionability: 90,
            reading_cost_fit: 90,
            risk_uncertainty: 10,
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
            topic_relevance: 99,
            information_density: 50,
            source_quality: 50,
            novelty: 50,
            timeliness: 50,
            actionability: 20,
            reading_cost_fit: 20,
            risk_uncertainty: 50,
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

test("filterArticlesForModule keeps only unread partial-progress items for continue reading", () => {
  const filtered = filterArticlesForModule(
    [
      article(1, { status: "unread", readProgress: 0, starred: true }),
      article(2, { status: "unread", readProgress: 0.4 }),
      article(3, { status: "read", readProgress: 0.4 }),
      article(4, { status: "unread", readProgress: 1 }),
    ],
    "read-later",
  );
  assert.deepEqual(filtered.map((item) => item.id), [2]);
});

test("filterArticlesForModule keeps candidate and continue-reading queues distinct", () => {
  const items = [
    article(1, { status: "unread", starred: false, project: false, readProgress: 0 }),
    article(2, { status: "read", starred: false, project: true, readProgress: 1 }),
    article(3, { status: "unread", starred: true, project: false, readProgress: 0 }),
    article(4, { status: "unread", starred: false, project: false, readProgress: 0.5 }),
  ];

  assert.deepEqual(filterArticlesForModule(items, "unread").map((item) => item.id), [1, 3, 4]);
  assert.deepEqual(filterArticlesForModule(items, "read").map((item) => item.id), [2]);
  assert.deepEqual(filterArticlesForModule(items, "starred").map((item) => item.id), [3]);
  assert.deepEqual(filterArticlesForModule(items, "project").map((item) => item.id), [2]);
  assert.deepEqual(filterArticlesForModule(items, "read-later").map((item) => item.id), [4]);
});

test("filterHiddenFeedsForModule hides feeds only in default modules", () => {
  const articles = [
    article(1, { feedHidden: true }),
    article(2, { feedHidden: false }),
  ];

  assert.deepEqual(filterHiddenFeedsForModule(articles, "all").map((item) => item.id), [2]);
  assert.deepEqual(filterHiddenFeedsForModule(articles, "technical").map((item) => item.id), [2]);
  assert.deepEqual(filterHiddenFeedsForModule(articles, "starred").map((item) => item.id), [1, 2]);
  assert.deepEqual(filterHiddenFeedsForModule(articles, "project").map((item) => item.id), [1, 2]);
});

test("sortArticlesForModule demotes low quality feeds before normal sorting", () => {
  const sorted = sortArticlesForModule(
    [
      article(1, {
        publishedAt: "2026-05-14T00:00:00.000Z",
        feedQualityScore: 20,
      }),
      article(2, {
        publishedAt: "2026-05-13T00:00:00.000Z",
        feedQualityScore: 80,
      }),
    ],
    "all",
  );

  assert.deepEqual(sorted.map((item) => item.id), [2, 1]);
});

test("explicit latest sorting keeps recency before feed quality", () => {
  const sorted = sortArticlesForModule(
    [
      article(1, {
        publishedAt: "2026-05-14T00:00:00.000Z",
        feedQualityScore: 20,
      }),
      article(2, {
        publishedAt: "2026-05-13T00:00:00.000Z",
        feedQualityScore: 80,
      }),
    ],
    "all",
    "latest",
  );

  assert.deepEqual(sorted.map((item) => item.id), [1, 2]);
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

test("sanitizeArticleHtml stamps paragraph anchors for citation jump", () => {
  const html = sanitizeArticleHtml(
    "<p>First paragraph about Rust.</p><p>Second about LLM agents.</p>",
  );
  assert.match(html, /data-paragraph-id="1"/);
  assert.match(html, /data-paragraph-id="2"/);
  assert.match(html, /id="p-1"/);
});

test("sanitizeArticleHtml removes script tags and inline event handlers", () => {
  const html = sanitizeArticleHtml('<p onclick="bad()">Hi</p><script>alert(1)</script>');
  assert.equal(html.includes("<script"), false);
  assert.equal(html.includes("onclick"), false);
  assert.match(html, /Hi/);
});

test("sanitizeArticleHtml keeps image hardening while adding lazy render attributes", () => {
  const html = sanitizeArticleHtml(
    '<p><img src="https://example.com/a.jpg" alt="A" onerror="bad()"><a href="javascript:bad()">bad</a></p>',
  );

  assert.match(html, /<img src="https:\/\/example.com\/a.jpg" alt="A" loading="lazy" decoding="async" \/>/);
  assert.equal(html.includes("onerror"), false);
  assert.equal(html.includes("javascript:"), false);
  assert.equal(html.includes("<script"), false);
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
