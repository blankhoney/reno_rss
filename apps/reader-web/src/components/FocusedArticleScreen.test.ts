import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FocusedArticleScreen } from "./FocusedArticleScreen";

test("FocusedArticleScreen starts with the reading skeleton", () => {
  const html = renderToStaticMarkup(
    React.createElement(FocusedArticleScreen, {
      articleId: 42,
      currentLang: "zh",
      returnHref: "/?module=all&sort=default&lang=zh&article=42",
    }),
  );

  assert.match(html, /focusArticleSkeleton/);
  assert.match(html, /返回工作台/);
  assert.doesNotMatch(html, /正在加载文章/);
});
