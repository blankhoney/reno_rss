import assert from "node:assert/strict";
import test from "node:test";
import { compositeCssLayers, contrastRatio, parseCssRgb } from "../../e2e/support/color";

test("CSS rgb parsing preserves floating channels and computes the dark focus ratio", () => {
  assert.deepEqual(parseCssRgb("rgb(34.02, 30.240000000000002, 23.68)"), [34.02, 30.240000000000002, 23.68, 1]);
  assert.ok(Math.abs(contrastRatio("rgb(224, 138, 74)", "rgb(34.02, 30.240000000000002, 23.68)") - 6.2275) < 0.0001);
});

test("CSS rgb parsing supports comma and modern alpha syntax", () => {
  assert.deepEqual(parseCssRgb("rgba(34, 30.5, 24, .25)"), [34, 30.5, 24, 0.25]);
  assert.deepEqual(parseCssRgb("rgb(34.02 30.24 23.68 / 12.5%)"), [34.02, 30.24, 23.68, 0.125]);
  assert.deepEqual(parseCssRgb("rgb(10% 20% 30%)"), [25.5, 51, 76.5, 1]);
});

test("alpha layer composition preserves fractional channels", () => {
  const composite = compositeCssLayers(["rgba(36, 32, 25, 0.78)", "rgb(27, 24, 19)"]);
  assert.deepEqual(composite, [34.02, 30.240000000000002, 23.68, 1]);
  assert.ok(Math.abs(contrastRatio("#e08a4a", `rgb(${composite[0]}, ${composite[1]}, ${composite[2]})`) - 6.2275) < 0.0001);
});

test("CSS rgb parsing fails closed for malformed and out-of-range colors", () => {
  for (const color of [
    "rgb(34.02.1, 30, 24)",
    "rgb(256, 30, 24)",
    "rgba(34, 30, 24, 1.01)",
    "rgb(34 30 / .5)",
    "not-a-color",
  ]) {
    assert.throws(() => parseCssRgb(color), /CSS|Expected/);
  }
  assert.throws(() => contrastRatio("rgb(224, 138, 74)", "rgba(27, 24, 19, .5)"), /opaque/);
});
