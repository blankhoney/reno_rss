import assert from "node:assert/strict";
import test from "node:test";
import { buildTextQuoteAnchor } from "./annotationAnchor";
import { applyHighlightMarks, applyHighlightMarksWithResolution, colorClassFor } from "./highlights";

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

test("anchored marks follow their context after repeated text shifts instead of marking the first quote", () => {
  const originalText = "Opening repeated quote.Intended context: repeated quote. Closing.";
  const targetStart = originalText.lastIndexOf("repeated quote");
  const anchor = buildTextQuoteAnchor(originalText, targetStart, targetStart + "repeated quote".length, 32);

  assert.ok(anchor);
  const result = applyHighlightMarksWithResolution(
    "<p>New preface. Opening repeated quote.</p><p>Intended context: repeated quote. Closing.</p>",
    [{ id: 9, selectedText: "repeated quote", color: "blue", anchor }],
  );

  assert.match(result.html, /Opening repeated quote\.<\/p><p>Intended context: <mark[^>]*data-annotation-id="9"[^>]*>repeated quote<\/mark>/);
  assert.deepEqual(result.unresolvedAnnotationIds, []);
});

test("anchored marks expose unresolved ids when the stored context is ambiguous", () => {
  const result = applyHighlightMarksWithResolution(
    "<p>same context: repeated quote. same context: repeated quote.</p>",
    [{
      id: 12,
      selectedText: "repeated quote",
      color: "yellow",
      anchor: {
        kind: "text-quote",
        version: 1,
        exact: "repeated quote",
        prefix: "same context: ",
        suffix: ".",
        start: 0,
        end: "repeated quote".length,
      },
    }],
  );

  assert.doesNotMatch(result.html, /data-annotation-id="12"/);
  assert.deepEqual(result.unresolvedAnnotationIds, [12]);
});

test("longer quotes are marked before shorter nested fragments", () => {
  const html = "<p>The quick brown fox jumps over the lazy dog.</p>";
  const result = applyHighlightMarksWithResolution(html, [
    { id: 1, selectedText: "fox", color: "green" },
    { id: 2, selectedText: "quick brown fox jumps", color: "blue" },
  ]);

  assert.match(result.html, /data-annotation-id="2"/);
  assert.match(result.html, /data-annotation-id="1"/);
  const outerStart = result.html.indexOf('data-annotation-id="2"');
  const innerStart = result.html.indexOf('data-annotation-id="1"');
  assert.ok(outerStart < innerStart, "longer mark must wrap the shorter one");
  assert.deepEqual(result.unresolvedAnnotationIds, []);
});
