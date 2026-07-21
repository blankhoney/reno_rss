import assert from "node:assert/strict";
import test from "node:test";

import { ARTICLE_DETAIL_CACHE, PRIVATE_CACHE_OWNER_KEY } from "@/lib/pwa/cacheKey";
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

function withPwaStorage(owner: string | null) {
  const originalCaches = Object.getOwnPropertyDescriptor(globalThis, "caches");
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const values = new Map<string, string>();
  const deletedCaches: string[] = [];
  if (owner != null) values.set(PRIVATE_CACHE_OWNER_KEY, owner);

  Object.defineProperty(globalThis, "caches", {
    configurable: true,
    value: {
      delete: async (name: string) => {
        deletedCaches.push(name);
        return true;
      },
    },
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    },
  });

  return {
    deletedCaches,
    values,
    restore() {
      if (originalCaches == null) delete (globalThis as { caches?: unknown }).caches;
      else Object.defineProperty(globalThis, "caches", originalCaches);
      if (originalStorage == null) delete (globalThis as { localStorage?: unknown }).localStorage;
      else Object.defineProperty(globalThis, "localStorage", originalStorage);
    },
  };
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

test("auth transitions clear private article cache when the owner changes or ends", async () => {
  const pwa = withPwaStorage("user-a");
  const restoreFetch = withMockFetch((input) => {
    if (input === "/api/auth/login") {
      return new Response(
        JSON.stringify({
          user: {
            id: "user-b",
            display_name: "Babbage",
            role: "user",
            created_at: "2026-06-25T00:00:00Z",
            last_seen_at: null,
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (input === "/api/auth/me") {
      return new Response(
        JSON.stringify({ error: { code: "unauthenticated", message: "Authentication required" } }),
        { status: 401, headers: { "content-type": "application/json" } },
      );
    }
    return new Response(null, { status: 204 });
  });

  try {
    await loginWithDisplayName("Babbage");
    assert.deepEqual(pwa.deletedCaches, [ARTICLE_DETAIL_CACHE]);
    assert.equal(pwa.values.get(PRIVATE_CACHE_OWNER_KEY), "user-b");

    await getCurrentSession();
    assert.deepEqual(pwa.deletedCaches, [ARTICLE_DETAIL_CACHE, ARTICLE_DETAIL_CACHE]);
    assert.equal(pwa.values.has(PRIVATE_CACHE_OWNER_KEY), false);

    await logoutSession();
    assert.deepEqual(pwa.deletedCaches, [ARTICLE_DETAIL_CACHE, ARTICLE_DETAIL_CACHE, ARTICLE_DETAIL_CACHE]);
  } finally {
    restoreFetch();
    pwa.restore();
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
