"use client";

import type { FormEvent, ReactNode } from "react";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  getCurrentSession,
  loginWithDisplayName,
  logoutSession,
  recoverSession,
  type AuthUser,
} from "@/lib/api/auth";

type AuthMode = "login" | "recover";
type AuthStatus = "loading" | "unauthenticated" | "authenticated";

type AuthSessionViewProps = {
  status: AuthStatus;
  mode: AuthMode;
  user?: AuthUser | null;
  recoveryCode: string | null;
  error: string | null;
  isSubmitting: boolean;
  children?: ReactNode;
  onLoginSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRecoverSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onLogout: () => void;
  onModeChange: (mode: AuthMode) => void;
  onDismissRecoveryCode: () => void;
};

export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === "invalid_recovery_code") {
    return "恢复码无效";
  }
  const message = error instanceof Error ? error.message : "auth_failed";
  if (message === "display_name_required") return "请输入显示名称";
  if (message === "recovery_code_required") return "请输入恢复码";
  if (message === "invalid_recovery_code") return "恢复码无效";
  if (message === "Authentication required") return "请先登录";
  return message.trim() || "认证失败";
}

export function AuthSessionView({
  status,
  mode,
  user = null,
  recoveryCode,
  error,
  isSubmitting,
  children,
  onLoginSubmit,
  onRecoverSubmit,
  onLogout,
  onModeChange,
  onDismissRecoveryCode,
}: AuthSessionViewProps) {
  if (status === "loading") {
    return (
      <main className="authGate" aria-busy="true">
        <section className="authCard" aria-label="会话状态">
          <p className="authEyebrow">AI Reader</p>
          <h1 className="authTitle">正在验证会话</h1>
          <p className="authLead">读取本机浏览器会话后进入阅读工作台。</p>
        </section>
      </main>
    );
  }

  if (status === "authenticated" && user != null) {
    return (
      <>
        <div className="authSessionBar" aria-label="当前会话">
          <div>
            <span className="authSessionLabel">当前用户</span>
            <strong>{user.displayName}</strong>
            <span className="authRoleBadge">{user.role}</span>
          </div>
          <button type="button" className="authSecondaryButton" onClick={onLogout} disabled={isSubmitting}>
            退出登录
          </button>
        </div>
        {recoveryCode ? (
          <section className="authRecovery" aria-label="恢复码">
            <div>
              <span>恢复码</span>
              <code className="authRecoveryCode">{recoveryCode}</code>
            </div>
            <button type="button" className="authSecondaryButton" onClick={onDismissRecoveryCode}>
              我已保存
            </button>
          </section>
        ) : null}
        {children}
      </>
    );
  }

  return (
    <main className="authGate">
      <section className="authCard" aria-labelledby="auth-title">
        <p className="authEyebrow">AI Reader</p>
        <h1 id="auth-title" className="authTitle">
          {mode === "login" ? "登录 AI Reader" : "恢复会话"}
        </h1>
        <p className="authLead">
          {mode === "login" ? "输入显示名称创建或继续本机阅读会话。" : "使用恢复码找回已有阅读会话。"}
        </p>
        {mode === "login" ? (
          <form className="authForm" onSubmit={onLoginSubmit}>
            <label className="authField">
              <span>显示名称</span>
              <input className="authTextInput" name="displayName" autoComplete="name" required />
            </label>
            <div className="authActions">
              <button type="submit" className="authPrimaryButton" disabled={isSubmitting}>
                {isSubmitting ? "登录中" : "进入阅读"}
              </button>
              <button type="button" className="authSecondaryButton" onClick={() => onModeChange("recover")}>
                恢复已有会话
              </button>
            </div>
          </form>
        ) : (
          <form className="authForm" onSubmit={onRecoverSubmit}>
            <label className="authField">
              <span>恢复码</span>
              <input className="authTextInput" name="recoveryCode" autoComplete="off" required />
            </label>
            <div className="authActions">
              <button type="submit" className="authPrimaryButton" disabled={isSubmitting}>
                {isSubmitting ? "恢复中" : "恢复会话"}
              </button>
              <button type="button" className="authSecondaryButton" onClick={() => onModeChange("login")}>
                返回登录
              </button>
            </div>
          </form>
        )}
        {error ? <p className="authError">{error}</p> : null}
      </section>
    </main>
  );
}

export function AuthSessionGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [mode, setMode] = useState<AuthMode>("login");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [recoveryCode, setRecoveryCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let active = true;

    getCurrentSession()
      .then((session) => {
        if (!active) return;
        if (session == null) {
          setStatus("unauthenticated");
          return;
        }
        setUser(session.user);
        setStatus("authenticated");
      })
      .catch((caught) => {
        if (!active) return;
        setError(authErrorMessage(caught));
        setStatus("unauthenticated");
      });

    return () => {
      active = false;
    };
  }, []);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsSubmitting(true);
    setError(null);
    setRecoveryCode(null);
    try {
      const session = await loginWithDisplayName(String(form.get("displayName") ?? ""));
      setUser(session.user);
      setRecoveryCode(session.recoveryCode);
      setStatus("authenticated");
    } catch (caught) {
      setError(authErrorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitRecover(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setIsSubmitting(true);
    setError(null);
    setRecoveryCode(null);
    try {
      const session = await recoverSession(String(form.get("recoveryCode") ?? ""));
      setUser(session.user);
      setRecoveryCode(session.recoveryCode);
      setStatus("authenticated");
    } catch (caught) {
      setError(authErrorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function logout() {
    setIsSubmitting(true);
    setError(null);
    try {
      await logoutSession();
      setUser(null);
      setRecoveryCode(null);
      setStatus("unauthenticated");
      setMode("login");
    } catch (caught) {
      setError(authErrorMessage(caught));
    } finally {
      setIsSubmitting(false);
    }
  }

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode);
    setError(null);
    setRecoveryCode(null);
  }

  return (
    <AuthSessionView
      status={status}
      mode={mode}
      user={user}
      recoveryCode={recoveryCode}
      error={error}
      isSubmitting={isSubmitting}
      onLoginSubmit={(event) => void submitLogin(event)}
      onRecoverSubmit={(event) => void submitRecover(event)}
      onLogout={() => void logout()}
      onModeChange={changeMode}
      onDismissRecoveryCode={() => setRecoveryCode(null)}
    >
      {children}
    </AuthSessionView>
  );
}
