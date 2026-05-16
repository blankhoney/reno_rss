import assert from "node:assert/strict";
import test from "node:test";
import {
  buildScoringServiceAuthHeader,
  buildScoringServiceUrl,
  parseScoreRequestBody,
} from "./service-client";

test("buildScoringServiceUrl joins base URL and internal score endpoint", () => {
  assert.equal(
    buildScoringServiceUrl("http://scoring-service-staging:8000/", "/internal/score-entry"),
    "http://scoring-service-staging:8000/internal/score-entry",
  );
});

test("buildScoringServiceAuthHeader uses HTTP Basic when credentials are set", () => {
  assert.equal(
    buildScoringServiceAuthHeader("scorer", "secret"),
    `Basic ${Buffer.from("scorer:secret").toString("base64")}`,
  );
  assert.equal(buildScoringServiceAuthHeader(undefined, "secret"), undefined);
});

test("parseScoreRequestBody defaults realtime scoring to force mode", () => {
  assert.deepEqual(parseScoreRequestBody(null), { force: true });
  assert.deepEqual(parseScoreRequestBody({ force: false }), { force: false });
  assert.deepEqual(parseScoreRequestBody({ force: "nope" }), { force: true });
});
