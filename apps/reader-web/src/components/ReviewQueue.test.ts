import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ReviewQueue } from "./ReviewQueue";

test("ReviewQueue exposes a stable accessible refresh control", () => {
  const html = renderToStaticMarkup(React.createElement(ReviewQueue));
  assert.match(html, /aria-label="刷新队列"/);
  assert.match(html, />刷新队列<\/button>/);
});

test("ReviewQueue synchronously owns refresh and review attempts", () => {
  const source = readFileSync(new URL("./ReviewQueue.tsx", import.meta.url), "utf8");
  assert.match(source, /if \(manual && pendingRefreshRef\.current != null\) return;/);
  assert.match(source, /pendingRefreshRef\.current = attempt;\s+setPendingRefreshSeq\(attempt\.requestSeq\);/);
  assert.match(source, /ownsAnnotationLoad\(attempt/);
  assert.match(source, /mutationEpochRef\.current \+= 1;\s+setItems/);
  assert.match(source, /if \(!mountedRef\.current \|\| pendingReviewRef\.current != null\) return;/);
  assert.match(source, /pendingReviewRef\.current = attempt;\s+setBusyAttempt\(attempt\);/);
  assert.match(source, /if \(!ownsReviewAttempt\(attempt\)\) return;/);
  assert.match(source, /setBusyAttempt\(\(current\) => current\?\.seq === attempt\.seq && current\.id === attempt\.id \? null : current\)/);
  assert.match(source, /const active = document\.activeElement;/);
  assert.match(source, /restoreRefreshFocusRef\.current = attempt\.hadFocus;\s+setPendingRefreshSeq/);
  assert.match(source, /if \(pendingRefreshSeq != null \|\| !restoreRefreshFocusRef\.current\) return;/);
  assert.match(source, /active === document\.body \|\| active === button \|\| active\?\.isConnected === false/);
  assert.match(source, /button\.focus\(\{ preventScroll: true \}\)/);
  assert.match(source, /aria-label="刷新队列"[\s\S]*aria-busy=\{pendingRefreshSeq != null\}[\s\S]*disabled=\{pendingRefreshSeq != null\}/);
});
