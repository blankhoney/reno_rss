import assert from "node:assert/strict";
import test from "node:test";
import { applyHighlightMarks, colorClassFor } from "./highlights";

test("applyHighlightMarks wraps first matching quote with color class", () => {
  const html = "<p id=\"p-1\" data-paragraph-id=\"1\">Rust async runtime is great.</p>";
  const out = applyHighlightMarks(html, [
    { id: 9, selectedText: "async runtime", color: "blue" },
  ]);
  assert.match(out, /data-annotation-id="9"/);
  assert.match(out, /articleHighlight hl-blue/);
  assert.match(out, /async runtime/);
});

test("colorClassFor defaults to yellow", () => {
  assert.equal(colorClassFor(null), "hl-yellow");
  assert.equal(colorClassFor("pink"), "hl-pink");
});
