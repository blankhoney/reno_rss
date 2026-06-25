import assert from "node:assert/strict";
import test from "node:test";

import { getCurrentSession, loginWithDisplayName, logoutSession, recoverSession } from "./auth";

function withMockFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> | Response,
): () => void {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = handler as typeof fetch;
  return () => {
    globalThis.fetch = originalFetch;
  };
}

function headerValue(headers: HeadersInit | undefined, name: string): string | null {
  if (!headers) return null;
  return new Headers(headers).get(name);
}

test("loginWithDisplayName posts display name and returns recovery code", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((input, init) => {
    capturedInput = input;
    capturedInit = init;
    return new Response(
      JSON.stringify({
        user: {
          id: "1",
          display_name: "Ada",
          role: "user",
          created_at: "2026-06-25T00:00:00Z",
          last_seen_at: null,
        },
        recovery_code: "recover-ada-123456",
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });

  try {
    const session = await loginWithDisplayName("  Ada  ");

    assert.equal(capturedInput, "/api/auth/login");
    assert.equal(capturedInit?.method, "POST");
    assert.equal(capturedInit?.credentials, "include");
    assert.equal(headerValue(capturedInit?.headers, "content-type"), "application/json");
    assert.equal(capturedInit?.body, JSON.stringify({ display_name: "Ada" }));
    assert.equal(session.user.displayName, "Ada");
    assert.equal(session.recoveryCode, "recover-ada-123456");
  } finally {
    restoreFetch();
  }
});

test("getCurrentSession returns null for unauthenticated users", async () => {
  const restoreFetch = withMockFetch(() => {
    return new Response(
      JSON.stringify({
        error: {
          code: "unauthenticated",
          message: "Authentication required",
          details: {},
        },
      }),
      { status: 401, headers: { "content-type": "application/json" } },
    );
  });

  try {
    assert.equal(await getCurrentSession(), null);
  } finally {
    restoreFetch();
  }
});

test("recoverSession posts recovery code and returns the refreshed code", async () => {
  const restoreFetch = withMockFetch((_input, init) => {
    return new Response(
      JSON.stringify({
        user: {
          id: "2",
          display_name: "Grace",
          role: "admin",
          created_at: "2026-06-25T00:00:00Z",
          last_seen_at: "2026-06-25T01:00:00Z",
        },
        recovery_code: "recover-grace-7890",
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });

  try {
    const session = await recoverSession("recover-old-code");

    assert.equal(session.user.role, "admin");
    assert.equal(session.recoveryCode, "recover-grace-7890");
  } finally {
    restoreFetch();
  }
});

test("logoutSession sends a bodyless POST", async () => {
  let capturedInput: RequestInfo | URL | undefined;
  let capturedInit: RequestInit | undefined;
  const restoreFetch = withMockFetch((input, init) => {
    capturedInput = input;
    capturedInit = init;
    return new Response(null, { status: 204 });
  });

  try {
    await logoutSession();

    assert.equal(capturedInput, "/api/auth/logout");
    assert.equal(capturedInit?.method, "POST");
    assert.equal(capturedInit?.credentials, "include");
    assert.equal(headerValue(capturedInit?.headers, "content-type"), null);
    assert.equal(capturedInit?.body, undefined);
  } finally {
    restoreFetch();
  }
});
