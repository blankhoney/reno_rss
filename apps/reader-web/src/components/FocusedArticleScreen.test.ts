import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FocusedArticleScreen, shouldReloadForArticleChange } from "./FocusedArticleScreen";

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

test("shouldReloadForArticleChange keeps null broadcast semantics", () => {
  assert.equal(shouldReloadForArticleChange(null, 42), true);
  assert.equal(shouldReloadForArticleChange({}, 42), true);
  assert.equal(shouldReloadForArticleChange({ articleId: null }, 42), true);
});

test("shouldReloadForArticleChange reloads only matching article ids", () => {
  assert.equal(shouldReloadForArticleChange({ articleId: 42 }, 42), true);
  assert.equal(shouldReloadForArticleChange({ articleId: 41 }, 42), false);
  assert.equal(shouldReloadForArticleChange({ articleId: "42" }, 42), false);
});
