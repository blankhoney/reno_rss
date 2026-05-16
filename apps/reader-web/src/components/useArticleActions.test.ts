import assert from "node:assert/strict";
import test from "node:test";
import { contentFetchResultMessage } from "./useArticleActions";

test("contentFetchResultMessage explains fetch-content outcomes", () => {
  assert.equal(
    contentFetchResultMessage({
      outcome: "applied",
      quality: "full",
      issue: null,
      textLength: 900,
    }),
    "全文已刷新，已切换到较完整正文",
  );
  assert.equal(
    contentFetchResultMessage({
      outcome: "rejected",
      reason: "blocked_or_error_page",
      issue: "blocked_or_error_page",
      textLength: 80,
    }),
    "源站返回错误页或登录墙，当前仍显示 RSS 片段",
  );
  assert.equal(
    contentFetchResultMessage({
      outcome: "failed",
      reason: "fetch_content_failed",
      issue: "fetch_failed",
      textLength: 0,
    }),
    "全文抓取失败，请打开原文阅读",
  );
});
