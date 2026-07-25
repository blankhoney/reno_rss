import {
  getCurrentSession,
  type AuthSession,
  type AuthUser,
} from "@/lib/api/auth";

export type CachedSession = {
  user: AuthUser;
  fetchedAt: number;
};

export const SESSION_CACHE_TTL_MS = 5 * 60_000;

let cachedSession: CachedSession | null = null;
let inFlightSession: Promise<AuthUser | null> | null = null;
let sessionGeneration = 0;

export function isSessionFresh(
  entry: CachedSession | null | undefined,
  now = Date.now(),
  ttlMs = SESSION_CACHE_TTL_MS,
): entry is CachedSession {
  if (entry == null) return false;
  const ageMs = now - entry.fetchedAt;
  return ageMs >= 0 && ageMs <= ttlMs;
}

export function readCachedSessionUser(now = Date.now()): AuthUser | null {
  return isSessionFresh(cachedSession, now) ? cachedSession.user : null;
}

export function primeSessionCache(user: AuthUser, fetchedAt = Date.now()) {
  sessionGeneration += 1;
  cachedSession = { user, fetchedAt };
}

export function clearSessionCache() {
  sessionGeneration += 1;
  cachedSession = null;
  inFlightSession = null;
}

export function fetchSessionUser(
  fetcher: () => Promise<AuthSession | null> = getCurrentSession,
): Promise<AuthUser | null> {
  if (inFlightSession != null) return inFlightSession;

  const requestGeneration = sessionGeneration;
  const request = fetcher()
    .then((session) => {
      if (requestGeneration !== sessionGeneration) {
        return readCachedSessionUser();
      }
      if (session == null) {
        cachedSession = null;
        return null;
      }
      cachedSession = { user: session.user, fetchedAt: Date.now() };
      return session.user;
    })
    .finally(() => {
      if (inFlightSession === request) {
        inFlightSession = null;
      }
    });

  inFlightSession = request;
  return request;
}
