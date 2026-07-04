import assert from "node:assert/strict";
import test from "node:test";
import { contentFetchJobMessage, translationJobMessage } from "./useArticleActions";

test("translationJobMessage explains translation job outcomes", () => {
  assert.equal(
    translationJobMessage({
      id: 11,
      jobType: "translate_article",
      status: "succeeded",
      progress: {},
      result: { outcome: "translated" },
      lastError: null,
      createdAt: "2026-06-25T00:00:00Z",
      updatedAt: "2026-06-25T00:00:01Z",
      completedAt: "2026-06-25T00:00:01Z",
    }),
    "全文翻译已完成",
  );
  assert.equal(
    translationJobMessage({
      id: 12,
      jobType: "translate_article",
      status: "failed",
      progress: {},
      result: {},
      lastError: "translation_failed",
      createdAt: "2026-06-25T00:00:00Z",
      updatedAt: "2026-06-25T00:00:01Z",
      completedAt: "2026-06-25T00:00:01Z",
    }),
    "全文翻译失败，请稍后重试",
  );
});

test("contentFetchJobMessage explains FastAPI fetch-content job outcomes", () => {
  assert.equal(
    contentFetchJobMessage({
      id: 9,
      jobType: "fetch_article_content",
      status: "succeeded",
      progress: {},
      result: { outcome: "applied", content_quality: "full" },
      lastError: null,
      createdAt: "2026-06-25T00:00:00Z",
      updatedAt: "2026-06-25T00:00:01Z",
      completedAt: "2026-06-25T00:00:01Z",
    }),
    "全文已刷新，已切换到较完整正文",
  );

  assert.equal(
    contentFetchJobMessage({
      id: 10,
      jobType: "fetch_article_content",
      status: "succeeded",
      progress: {},
      result: { outcome: "fallback", content_quality: "snippet" },
      lastError: null,
      createdAt: "2026-06-25T00:00:00Z",
      updatedAt: "2026-06-25T00:00:01Z",
      completedAt: "2026-06-25T00:00:01Z",
    }),
    "已尝试刷新全文，当前仍可能只有 RSS 片段",
  );
});
