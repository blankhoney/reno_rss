import assert from "node:assert/strict";
import test from "node:test";

import { buildTextQuoteAnchor, parseTextQuoteAnchor } from "./annotationAnchor";

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
