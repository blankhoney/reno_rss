import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ToastHost, clampToastQueue } from "./Toast";

test("ToastHost renders a status live region", () => {
  const html = renderToStaticMarkup(React.createElement(ToastHost));

  assert.match(html, /class="toastHost"/);
  assert.match(html, /role="status"/);
  assert.match(html, /aria-live="polite"/);
});

test("clampToastQueue keeps at most two latest toasts", () => {
  const queue = clampToastQueue([
    { id: 1, title: "one", variant: "success" },
    { id: 2, title: "two", variant: "info" },
    { id: 3, title: "three", variant: "error" },
  ]);

  assert.deepEqual(queue.map((item) => item.title), ["two", "three"]);
});
