import assert from "node:assert/strict";
import test from "node:test";
import {
  getDemoAccessConfig,
  performDemoLogin,
  requestAllowedByOrigin,
  shouldRenderDemoLanding,
  type DemoAccessConfig,
} from "./access";

const demoConfig: DemoAccessConfig = {
  enabled: true,
  username: "demo",
  password: "demo-reader-2026",
  autheliaBaseUrl: "https://auth.blankhoney.xyz",
  targetUrl: "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh",
  allowedOrigin: "https://staging-ai-reader.blankhoney.xyz",
};

function request(headers: Record<string, string> = {}) {
  return new Request("https://staging-ai-reader.blankhoney.xyz/api/demo-login", {
    method: "POST",
    headers,
  });
}

function responseWithCookies(cookies: string[]) {
  const headers = new Headers();
  for (const cookie of cookies) headers.append("set-cookie", cookie);
  return new Response("{}", { status: 200, headers });
}

test("getDemoAccessConfig reads demo env without requiring reader config", () => {
  const config = getDemoAccessConfig({
    DEMO_LANDING_ENABLED: "true",
    DEMO_USERNAME: "demo",
    DEMO_PASSWORD: "public-demo-password",
    DEMO_AUTHELIA_BASE_URL: "https://auth.example.test",
    DEMO_TARGET_URL: "https://staging-ai-reader.example.test/?module=all&sort=default&lang=zh",
    DEMO_ALLOWED_ORIGIN: "https://staging-ai-reader.example.test",
  });

  assert.equal(config.enabled, true);
  assert.equal(config.username, "demo");
  assert.equal(config.password, "public-demo-password");
  assert.equal(config.autheliaBaseUrl, "https://auth.example.test");
  assert.equal(config.targetUrl, "https://staging-ai-reader.example.test/?module=all&sort=default&lang=zh");
  assert.equal(config.allowedOrigin, "https://staging-ai-reader.example.test");
});

test("shouldRenderDemoLanding only allows an enabled empty-query root request", () => {
  assert.equal(shouldRenderDemoLanding({}, { enabled: true }), true);
  assert.equal(shouldRenderDemoLanding({ module: "all" }, { enabled: true }), false);
  assert.equal(shouldRenderDemoLanding({}, { enabled: false }), false);
});

test("requestAllowedByOrigin accepts only the staging origin or referer", () => {
  assert.equal(
    requestAllowedByOrigin(
      request({ origin: "https://staging-ai-reader.blankhoney.xyz" }),
      demoConfig.allowedOrigin,
    ),
    true,
  );
  assert.equal(
    requestAllowedByOrigin(
      request({ referer: "https://staging-ai-reader.blankhoney.xyz/" }),
      demoConfig.allowedOrigin,
    ),
    true,
  );
  assert.equal(
    requestAllowedByOrigin(request({ origin: "https://evil.example" }), demoConfig.allowedOrigin),
    false,
  );
  assert.equal(
    requestAllowedByOrigin(
      request({
        origin: "https://evil.example",
        referer: "https://staging-ai-reader.blankhoney.xyz/",
      }),
      demoConfig.allowedOrigin,
    ),
    false,
  );
  assert.equal(requestAllowedByOrigin(request(), demoConfig.allowedOrigin), false);
});

test("performDemoLogin uses server credentials and fixed external target URL", async () => {
  let capturedUrl = "";
  let capturedBody: unknown = null;
  const result = await performDemoLogin(
    request({
      origin: "https://staging-ai-reader.blankhoney.xyz",
      "content-type": "application/json",
    }),
    demoConfig,
    async (url, init) => {
      capturedUrl = String(url);
      capturedBody = JSON.parse(String(init?.body));
      return responseWithCookies([
        "authelia_session=abc; Path=/; Domain=blankhoney.xyz; HttpOnly; Secure",
        "second=value; Path=/; Secure",
      ]);
    },
  );

  assert.equal(capturedUrl, "https://auth.blankhoney.xyz/api/firstfactor");
  assert.deepEqual(capturedBody, {
    username: "demo",
    password: "demo-reader-2026",
    keepMeLoggedIn: true,
    targetURL: "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh",
    requestMethod: "GET",
  });
  assert.deepEqual(result, {
    ok: true,
    status: 303,
    location: "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh",
    cookies: [
      "authelia_session=abc; Path=/; Domain=blankhoney.xyz; HttpOnly; Secure",
      "second=value; Path=/; Secure",
    ],
  });
});

test("performDemoLogin rejects invalid origin before calling Authelia", async () => {
  let called = false;
  const result = await performDemoLogin(
    request({ origin: "https://evil.example" }),
    demoConfig,
    async () => {
      called = true;
      return responseWithCookies(["authelia_session=abc"]);
    },
  );

  assert.equal(called, false);
  assert.deepEqual(result, { ok: false, status: 403, error: "invalid_origin" });
});

test("performDemoLogin failures do not expose the demo password", async () => {
  const result = await performDemoLogin(
    request({ origin: "https://staging-ai-reader.blankhoney.xyz" }),
    demoConfig,
    async () => new Response("nope", { status: 401 }),
  );

  assert.equal(result.ok, false);
  assert.equal(JSON.stringify(result).includes("demo-reader-2026"), false);
});
