import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  ArticleListSkeleton,
  FocusedArticleSkeleton,
  WorkbenchRailSkeleton,
  WorkbenchStatsSkeleton,
} from "./Skeleton";

test("ArticleListSkeleton mirrors the paged article list size", () => {
  const html = renderToStaticMarkup(React.createElement(ArticleListSkeleton, { count: 12 }));

  assert.equal((html.match(/articleCardSkeleton/g) ?? []).length, 12);
  assert.match(html, /aria-label="文章加载中"/);
  assert.match(html, /aria-busy="true"/);
});

test("rail skeletons render separate recommendation and stats placeholders", () => {
  const railHtml = renderToStaticMarkup(React.createElement(WorkbenchRailSkeleton));
  const statsHtml = renderToStaticMarkup(React.createElement(WorkbenchStatsSkeleton));

  assert.match(railHtml, /右栏加载中/);
  assert.match(statsHtml, /统计加载中/);
  assert.equal((railHtml.match(/workbenchRailItemSkeleton/g) ?? []).length, 5);
});

test("FocusedArticleSkeleton preserves the return link and content shape", () => {
  const html = renderToStaticMarkup(
    React.createElement(FocusedArticleSkeleton, {
      returnHref: "/?module=all&sort=default&lang=zh&article=42",
    }),
  );

  assert.match(html, /返回工作台/);
  assert.match(html, /href="\/\?module=all&amp;sort=default&amp;lang=zh&amp;article=42"/);
  assert.match(html, /focusArticleSkeleton/);
});
