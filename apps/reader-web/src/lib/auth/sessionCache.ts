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
  cachedSession = { user, fetchedAt };
}

export function clearSessionCache() {
  cachedSession = null;
}

export function fetchSessionUser(
  fetcher: () => Promise<AuthSession | null> = getCurrentSession,
): Promise<AuthUser | null> {
  if (inFlightSession != null) return inFlightSession;

  inFlightSession = fetcher()
    .then((session) => {
      if (session == null) {
        clearSessionCache();
        return null;
      }
      primeSessionCache(session.user);
      return session.user;
    })
    .finally(() => {
      inFlightSession = null;
    });

  return inFlightSession;
}
