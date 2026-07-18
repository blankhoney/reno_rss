import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ModuleSidebar } from "./ModuleSidebar";

test("ModuleSidebar groups the navigation and keeps the active module visible", () => {
  const html = renderToStaticMarkup(
    React.createElement(ModuleSidebar, { currentModule: "project" }),
  );

  assert.match(html, /情报台/);
  assert.match(html, /今日情报/);
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
  assert.match(html, /data-group="intelligence"/);
  assert.match(html, /data-group="flow"/);
  assert.match(html, /data-group="clues"/);
  assert.match(html, /mobileTopbar/);
  assert.match(html, /aria-controls="mobile-module-drawer"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /themeToggle/);
});

test("ModuleSidebar marks 今日情报 active for home module", () => {
  const html = renderToStaticMarkup(
    React.createElement(ModuleSidebar, { currentModule: "home" }),
  );

  assert.match(html, /今日情报/);
  assert.match(html, /aria-current="page"/);
  assert.match(html, /module=home/);
});

test("ModuleSidebar exposes the FastAPI admin console as the management surface", () => {
  const html = renderToStaticMarkup(
    React.createElement(ModuleSidebar, { currentModule: "admin" }),
  );

  assert.match(html, /管理控制台/);
  assert.match(html, /aria-current="page"/);
  assert.doesNotMatch(html, /订阅源管理/);
});
