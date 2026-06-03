import assert from "node:assert/strict";
import test from "node:test";
import { POST } from "./route";

const originalEnv = { ...process.env };

function setDemoEnv() {
  process.env.DEMO_LANDING_ENABLED = "true";
  process.env.DEMO_USERNAME = "demo";
  process.env.DEMO_PASSWORD = "demo-reader-2026";
  process.env.DEMO_AUTHELIA_BASE_URL = "https://auth.blankhoney.xyz";
  process.env.DEMO_TARGET_URL =
    "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh";
  process.env.DEMO_ALLOWED_ORIGIN = "https://staging-ai-reader.blankhoney.xyz";
}

function restoreEnv() {
  process.env = { ...originalEnv };
}

function request(headers: Record<string, string> = {}) {
  return new Request("https://staging-ai-reader.blankhoney.xyz/api/demo-login", {
    method: "POST",
    headers,
    body: JSON.stringify({
      username: "attacker",
      password: "attacker-password",
      targetURL: "https://evil.example",
    }),
  });
}

function setCookies(response: Response): string[] {
  const headersWithCookies = response.headers as Headers & { getSetCookie?: () => string[] };
  if (typeof headersWithCookies.getSetCookie === "function") {
    return headersWithCookies.getSetCookie();
  }
  const cookie = response.headers.get("set-cookie");
  return cookie ? [cookie] : [];
}

test("POST /api/demo-login logs in with server-side demo credentials", async () => {
  setDemoEnv();
  const originalFetch = globalThis.fetch;
  let capturedUrl = "";
  let capturedBody: Record<string, unknown> | null = null;
  globalThis.fetch = (async (url, init) => {
    capturedUrl = String(url);
    capturedBody = JSON.parse(String(init?.body));
    const headers = new Headers();
    headers.append("set-cookie", "authelia_session=abc; Path=/; Domain=blankhoney.xyz");
    headers.append("set-cookie", "remember=def; Path=/; Domain=blankhoney.xyz");
    return new Response("{}", { status: 200, headers });
  }) as typeof fetch;

  try {
    const response = await POST(request({ origin: "https://staging-ai-reader.blankhoney.xyz" }));

    assert.equal(response.status, 303);
    assert.equal(
      response.headers.get("location"),
      "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh",
    );
    assert.equal(capturedUrl, "https://auth.blankhoney.xyz/api/firstfactor");
    assert.deepEqual(capturedBody, {
      username: "demo",
      password: "demo-reader-2026",
      keepMeLoggedIn: true,
      targetURL: "https://staging-ai-reader.blankhoney.xyz/?module=all&sort=default&lang=zh",
      requestMethod: "GET",
    });
    assert.deepEqual(setCookies(response), [
      "authelia_session=abc; Path=/; Domain=blankhoney.xyz",
      "remember=def; Path=/; Domain=blankhoney.xyz",
    ]);
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnv();
  }
});

test("POST /api/demo-login rejects non-staging origins", async () => {
  setDemoEnv();
  const response = await POST(request({ origin: "https://evil.example" }));
  const body = await response.text();
  restoreEnv();

  assert.equal(response.status, 403);
  assert.match(body, /invalid_origin/);
  assert.equal(body.includes("demo-reader-2026"), false);
});
