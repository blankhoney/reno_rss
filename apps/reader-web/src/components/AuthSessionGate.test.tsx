import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ApiError } from "@/lib/api/client";
import { AuthSessionView, authErrorMessage } from "./AuthSessionGate";
import type { AuthUser } from "@/lib/api/auth";

const user: AuthUser = {
  id: "1",
  displayName: "Ada",
  role: "admin",
  createdAt: "2026-06-25T00:00:00Z",
  lastSeenAt: null,
};

function render(props: Partial<React.ComponentProps<typeof AuthSessionView>> = {}) {
  return renderToStaticMarkup(
    React.createElement(
      AuthSessionView,
      {
        status: "unauthenticated",
        mode: "login",
        recoveryCode: null,
        error: null,
        isSubmitting: false,
        onLoginSubmit() {},
        onRecoverSubmit() {},
        onLogout() {},
        onModeChange() {},
        onDismissRecoveryCode() {},
        ...props,
      },
      React.createElement("div", { className: "child-marker" }, "Reader workbench"),
    ),
  );
}

test("AuthSessionView renders a loading session check", () => {
  const html = render({ status: "loading" });

  assert.match(html, /正在验证会话/);
  assert.doesNotMatch(html, /Reader workbench/);
});

test("AuthSessionView renders login and recover entry points when unauthenticated", () => {
  const html = render({ status: "unauthenticated", mode: "login" });

  assert.match(html, /登录 AI Reader/);
  assert.match(html, /显示名称/);
  assert.match(html, /恢复已有会话/);
  assert.doesNotMatch(html, /Reader workbench/);
});

test("AuthSessionView renders the recovery form when recovery mode is selected", () => {
  const html = render({ status: "unauthenticated", mode: "recover" });

  assert.match(html, /恢复会话/);
  assert.match(html, /恢复码/);
  assert.match(html, /返回登录/);
});

test("AuthSessionView shows role and logout controls for authenticated users", () => {
  const html = render({ status: "authenticated", user });

  assert.match(html, /Ada/);
  assert.match(html, /admin/);
  assert.match(html, /退出登录/);
  assert.match(html, /Reader workbench/);
});

test("AuthSessionView shows recovery code only when passed for the current session", () => {
  const withCode = render({
    status: "authenticated",
    user,
    recoveryCode: "recover-once-123456",
  });
  const withoutCode = render({ status: "authenticated", user, recoveryCode: null });

  assert.match(withCode, /recover-once-123456/);
  assert.doesNotMatch(withoutCode, /recover-once-123456/);
});

test("authErrorMessage translates FastAPI recovery errors by code", () => {
  assert.equal(
    authErrorMessage(
      new ApiError({
        status: 400,
        code: "invalid_recovery_code",
        message: "Invalid recovery code",
      }),
    ),
    "恢复码无效",
  );
});
