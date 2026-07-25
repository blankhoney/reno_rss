import assert from "node:assert/strict";
import test from "node:test";

import {
  buildTextQuoteAnchor,
  parseTextQuoteAnchor,
  resolveTextQuoteAnchor,
} from "./annotationAnchor";

test("buildTextQuoteAnchor disambiguates a repeated quote with bounded context", () => {
  const text = "alpha repeated beta repeated gamma";
  const start = text.lastIndexOf("repeated");

  const anchor = buildTextQuoteAnchor(text, start, start + "repeated".length, 6);

  assert.deepEqual(anchor, {
    kind: "text-quote",
    version: 1,
    exact: "repeated",
    prefix: " beta ",
    suffix: " gamma",
    start,
    end: start + "repeated".length,
  });
});

test("buildTextQuoteAnchor trims selection edges and rejects invalid ranges", () => {
  assert.deepEqual(buildTextQuoteAnchor("before  quote  after", 6, 15, 20), {
    kind: "text-quote",
    version: 1,
    exact: "quote",
    prefix: "before  ",
    suffix: "  after",
    start: 8,
    end: 13,
  });
  assert.equal(buildTextQuoteAnchor("text", 3, 2), null);
  assert.equal(buildTextQuoteAnchor("text", 0, 0), null);
});

test("parseTextQuoteAnchor accepts the versioned contract and rejects malformed data", () => {
  const valid = {
    kind: "text-quote",
    version: 1,
    exact: "quote",
    prefix: "before",
    suffix: "after",
    start: 7,
    end: 12,
  };

  assert.deepEqual(parseTextQuoteAnchor(valid), valid);
  assert.equal(parseTextQuoteAnchor({ ...valid, version: 2 }), null);
  assert.equal(parseTextQuoteAnchor({ ...valid, end: 7 }), null);
  assert.equal(parseTextQuoteAnchor({ ...valid, exact: "" }), null);
});

test("resolveTextQuoteAnchor restores only the context-proven repeated quote after a refresh", () => {
  const original = "Opening. Intended context: repeated quote. Later context: repeated quote.";
  const start = original.indexOf("repeated quote");
  const anchor = buildTextQuoteAnchor(original, start, start + "repeated quote".length, 32);

  assert.ok(anchor);
  assert.deepEqual(
    resolveTextQuoteAnchor("New preface. Opening. Intended context: repeated quote. Later context: repeated quote.", anchor),
    {
      status: "resolved",
      start: "New preface. Opening. Intended context: ".length,
      end: "New preface. Opening. Intended context: repeated quote".length,
    },
  );
});

test("resolveTextQuoteAnchor rejects ambiguous and missing anchors instead of choosing another quote", () => {
  const anchor = {
    kind: "text-quote" as const,
    version: 1 as const,
    exact: "repeated quote",
    prefix: "same context: ",
    suffix: ".",
    start: 0,
    end: "repeated quote".length,
  };

  assert.deepEqual(
    resolveTextQuoteAnchor("same context: repeated quote. same context: repeated quote.", anchor),
    { status: "ambiguous" },
  );
  assert.deepEqual(resolveTextQuoteAnchor("The quote changed completely.", anchor), { status: "not-found" });
});
