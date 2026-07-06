import assert from "node:assert/strict";
import test from "node:test";
import type { AuthSession, AuthUser } from "@/lib/api/auth";
import {
  clearSessionCache,
  fetchSessionUser,
  isSessionFresh,
  primeSessionCache,
  readCachedSessionUser,
  SESSION_CACHE_TTL_MS,
} from "./sessionCache";

const user: AuthUser = {
  id: "1",
  displayName: "Ada",
  role: "admin",
  createdAt: "2026-06-25T00:00:00Z",
  lastSeenAt: null,
};

test("isSessionFresh accepts only non-expired cache entries", () => {
  assert.equal(isSessionFresh(null, 1000), false);
  assert.equal(isSessionFresh({ user, fetchedAt: 1000 }, 1000), true);
  assert.equal(isSessionFresh({ user, fetchedAt: 1000 }, 1000 + SESSION_CACHE_TTL_MS), true);
  assert.equal(isSessionFresh({ user, fetchedAt: 1000 }, 1001 + SESSION_CACHE_TTL_MS), false);
  assert.equal(isSessionFresh({ user, fetchedAt: 1001 }, 1000), false);
});

test("session cache can be primed, read, expire, and cleared", () => {
  clearSessionCache();
  primeSessionCache(user, 1000);

  assert.equal(readCachedSessionUser(1000)?.displayName, "Ada");
  assert.equal(readCachedSessionUser(1001 + SESSION_CACHE_TTL_MS), null);

  clearSessionCache();
  assert.equal(readCachedSessionUser(1000), null);
});

test("fetchSessionUser deduplicates in-flight session requests", async () => {
  clearSessionCache();
  let calls = 0;
  const fetcher = async (): Promise<AuthSession> => {
    calls += 1;
    await new Promise((resolve) => setTimeout(resolve, 1));
    return { user, recoveryCode: "do-not-cache" };
  };

  const [first, second] = await Promise.all([
    fetchSessionUser(fetcher),
    fetchSessionUser(fetcher),
  ]);

  assert.equal(calls, 1);
  assert.equal(first?.displayName, "Ada");
  assert.equal(second?.displayName, "Ada");
  assert.equal(readCachedSessionUser()?.displayName, "Ada");
});

test("fetchSessionUser clears cached users when the API returns unauthenticated", async () => {
  primeSessionCache(user, Date.now());

  const result = await fetchSessionUser(async () => null);

  assert.equal(result, null);
  assert.equal(readCachedSessionUser(), null);
});
