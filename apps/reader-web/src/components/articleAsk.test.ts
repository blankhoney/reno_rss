import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "@/lib/api/client";
import { articleAskErrorMessage } from "./articleAsk";

test("articleAskErrorMessage explains content_required as a fetch-first action", () => {
  assert.equal(
    articleAskErrorMessage(
      new ApiError({
        status: 409,
        code: "content_required",
        message: "Article content is required before asking",
      }),
    ),
    "需要先刷新全文或等待摘要评分生成后再提问。",
  );
});

test("articleAskErrorMessage keeps other API errors readable", () => {
  assert.equal(
    articleAskErrorMessage(
      new ApiError({
        status: 404,
        code: "not_found",
        message: "Article not found",
      }),
    ),
    "Article not found",
  );
});
