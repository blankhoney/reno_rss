import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ScoreRing, tierColorVar, tierLabel } from "./ScoreRing";

test("ScoreRing renders an empty dashed ring for unscored articles", () => {
  const html = renderToStaticMarkup(React.createElement(ScoreRing, { value: null }));

  assert.match(html, /aria-label="未评分"/);
  assert.match(html, /scoreRingEmpty/);
  assert.match(html, /—/);
});

test("ScoreRing renders score fill, size class, and label", () => {
  const html = renderToStaticMarkup(
    React.createElement(ScoreRing, { value: 88, tier: "must_read", size: 66, label: "总分" }),
  );

  assert.match(html, /scoreRing66/);
  assert.match(html, /aria-label="总分 88"/);
  assert.match(html, /--ringFill:88%/);
  assert.match(html, /--ringColor:var\(--accent\)/);
});

test("ScoreRing exposes tier labels and color vars", () => {
  assert.equal(tierLabel("must_read"), "必读");
  assert.equal(tierLabel("read"), "推荐");
  assert.equal(tierLabel("skim"), "略读");
  assert.equal(tierLabel("skip"), "跳过");
  assert.equal(tierColorVar(null, 72), "--success");
  assert.equal(tierColorVar(null, 50), "--accent");
  assert.equal(tierColorVar(null, 20), "--warning");
});
