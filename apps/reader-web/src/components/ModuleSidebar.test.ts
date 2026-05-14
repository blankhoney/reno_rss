import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ModuleSidebar } from "./ModuleSidebar";

test("ModuleSidebar labels the native Miniflux states as the clue flow", () => {
  const html = renderToStaticMarkup(
    React.createElement(ModuleSidebar, { currentModule: "project" }),
  );

  assert.match(html, /新到/);
  assert.match(html, /候选/);
  assert.match(html, /已立项/);
  assert.match(html, /aria-current="page"/);
});
