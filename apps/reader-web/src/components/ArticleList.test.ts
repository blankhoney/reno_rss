import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ArticleList } from "./ArticleList";

test("ArticleList renders an explicit empty state", () => {
  const html = renderToStaticMarkup(
    React.createElement(ArticleList, {
      articles: [],
      currentModule: "all",
      selectedArticleId: null,
    }),
  );

  assert.match(html, /暂无文章/);
  assert.match(html, /当前模块没有可显示的文章/);
});
