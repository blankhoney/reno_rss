import assert from "node:assert/strict";
import test from "node:test";
import { selectionPreview, selectionTextWithinContainer } from "./selection";

test("selectionTextWithinContainer returns trimmed text for in-article selections", () => {
  const inside = {};
  const container = {
    contains(node: object) {
      return node === inside;
    },
  };
  const selection = {
    anchorNode: inside,
    focusNode: inside,
    rangeCount: 1,
    toString: () => "  selected text  ",
  };

  assert.equal(selectionTextWithinContainer(container as HTMLElement, selection as Selection), "selected text");
});

test("selectionTextWithinContainer ignores empty or external selections", () => {
  const inside = {};
  const outside = {};
  const container = {
    contains(node: object) {
      return node === inside;
    },
  };

  assert.equal(
    selectionTextWithinContainer(container as HTMLElement, {
      anchorNode: inside,
      focusNode: outside,
      rangeCount: 1,
      toString: () => "text",
    } as Selection),
    null,
  );
  assert.equal(
    selectionTextWithinContainer(container as HTMLElement, {
      anchorNode: inside,
      focusNode: inside,
      rangeCount: 1,
      toString: () => "   ",
    } as Selection),
    null,
  );
});

test("selectionPreview truncates long selected text", () => {
  assert.equal(selectionPreview("one   two   three", 20), "one two three");
  assert.equal(selectionPreview("abcdefghijklmnopqrstuvwxyz", 8), "abcdefgh...");
});
