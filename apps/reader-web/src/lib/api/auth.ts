import { ApiError, apiGet, apiPost } from "./client";

export type AuthUser = {
  id: string;
  displayName: string;
  role: string;
  createdAt: string;
  lastSeenAt: string | null;
};

export type AuthSession = {
  user: AuthUser;
  recoveryCode: string | null;
};

type UserPayload = {
  id: string;
  display_name: string;
  role: string;
  created_at: string;
  last_seen_at: string | null;
};

type SessionPayload = {
  user: UserPayload;
  recovery_code?: string | null;
};

function normalizeUser(user: UserPayload): AuthUser {
  return {
    id: user.id,
    displayName: user.display_name,
    role: user.role,
    createdAt: user.created_at,
    lastSeenAt: user.last_seen_at,
  };
}

function normalizeSession(payload: SessionPayload): AuthSession {
  return {
    user: normalizeUser(payload.user),
    recoveryCode: payload.recovery_code ?? null,
  };
}

export async function getCurrentSession(): Promise<AuthSession | null> {
  try {
    const payload = await apiGet<{ user: UserPayload }>("/api/auth/me");
    return normalizeSession({ user: payload.user });
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

export async function loginWithDisplayName(displayName: string): Promise<AuthSession> {
  const normalized = displayName.trim();
  if (normalized.length === 0) {
    throw new Error("display_name_required");
  }
  const payload = await apiPost<SessionPayload, { display_name: string }>("/api/auth/login", {
    display_name: normalized,
  });
  return normalizeSession(payload);
}

export async function recoverSession(recoveryCode: string): Promise<AuthSession> {
  const normalized = recoveryCode.trim();
  if (normalized.length === 0) {
    throw new Error("recovery_code_required");
  }
  const payload = await apiPost<SessionPayload, { recovery_code: string }>("/api/auth/recover", {
    recovery_code: normalized,
  });
  return normalizeSession(payload);
}

export async function logoutSession(): Promise<void> {
  await apiPost<void, undefined>("/api/auth/logout");
}
