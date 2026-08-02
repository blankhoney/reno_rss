import assert from "node:assert/strict";
import test from "node:test";
import {
  buildFocusReadHref,
  buildWorkbenchHref,
  parseArticleId,
  parseCursorTrail,
  serializeCursorTrail,
} from "./navigation";

test("article route IDs accept only positive safe integer segments", () => {
  assert.equal(parseArticleId("7"), 7);
  assert.equal(parseArticleId("007"), 7);

  for (const raw of ["", "7abc", "7.9", "+7", " 7", "7 ", "0", "-1", String(Number.MAX_SAFE_INTEGER + 1)]) {
    assert.equal(parseArticleId(raw), null, `expected ${raw} to be rejected`);
  }
});

test("cursor trails round-trip only valid opaque cursor stacks", () => {
  const trail = [null, "cursor-two", "cursor-three"];
  const serialized = serializeCursorTrail(trail);

  assert.equal(serialized, '[null,"cursor-two","cursor-three"]');
  assert.deepEqual(parseCursorTrail(serialized), trail);
  assert.deepEqual(parseCursorTrail('["missing-root"]'), [null]);
  assert.deepEqual(parseCursorTrail('[null,""]'), [null]);
  assert.deepEqual(parseCursorTrail("not-json"), [null]);
});

test("workbench links preserve query, trail, and return article without cluttering page one", () => {
  assert.equal(
    buildWorkbenchHref({ module: "all", sort: "default", lang: "zh" }),
    "?module=all&sort=default&lang=zh",
  );

  const href = buildWorkbenchHref({
    module: "all",
    sort: "latest",
    lang: "original",
    query: "  fusion  ",
    cursorStack: [null, "cursor-two"],
    articleId: 42,
  });
  const params = new URLSearchParams(href.slice(1));
  assert.equal(params.get("module"), "all");
  assert.equal(params.get("sort"), "latest");
  assert.equal(params.get("lang"), "original");
  assert.equal(params.get("q"), "fusion");
  assert.deepEqual(parseCursorTrail(params.get("trail")), [null, "cursor-two"]);
  assert.equal(params.get("article"), "42");
  assert.equal(
    buildFocusReadHref(42, { module: "all", sort: "latest", lang: "zh", cursorStack: [null, "cursor-two"] }),
    `/read/42?module=all&sort=latest&lang=zh&trail=${encodeURIComponent('[null,"cursor-two"]')}`,
  );
});
