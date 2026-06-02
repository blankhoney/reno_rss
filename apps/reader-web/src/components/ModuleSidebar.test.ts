import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ModuleSidebar } from "./ModuleSidebar";

test("ModuleSidebar groups the navigation and keeps the active module visible", () => {
  const html = renderToStaticMarkup(
    React.createElement(ModuleSidebar, { currentModule: "project" }),
  );

  assert.match(html, /信息流/);
  assert.match(html, /线索流/);
  assert.match(html, /评分维度/);
  assert.match(html, /管理/);
  assert.match(html, /新到/);
  assert.match(html, /候选/);
  assert.match(html, /已立项/);
  assert.match(html, /aria-current="page"/);
  assert.match(html, /GitHub 源码/);
  assert.match(html, /href="https:\/\/github.com\/blankhoney\/reno_rss"/);
  assert.match(html, /target="_blank"/);
  assert.match(html, /rel="noreferrer noopener"/);
});

test("ModuleSidebar enables feed management", () => {
  const html = renderToStaticMarkup(
    React.createElement(ModuleSidebar, { currentModule: "feeds" }),
  );

  assert.match(html, /订阅源管理/);
  assert.match(html, /aria-current="page"/);
  assert.doesNotMatch(html, /即将推出/);
});
