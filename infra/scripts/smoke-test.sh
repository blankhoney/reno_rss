#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Purpose:
#   Verify a freshly deployed staging or production stack is reachable, that prod
#   fails closed, and that the staging public-demo boundary holds (anonymous users
#   get a user-scoped session while admin endpoints stay protected).
#
# Usage:
#   bash infra/scripts/smoke-test.sh staging
#   bash infra/scripts/smoke-test.sh prod
#
# Arguments:
#   $1  ENV  Environment name; must be staging or prod.
#
# Environment:
#   Reads DOMAIN and service configuration from the repository .env file.
#
# Exit codes:
#   0 when containers are running, health endpoints respond, the env-specific
#   anonymous auth boundary holds (prod 401; staging articles 200 / admin 403),
#   and on staging the app shell is publicly served.
#   Non-zero on invalid ENV, missing/risky containers, failed health checks, or
#   broken auth boundaries.
#
# Side effects:
#   Creates temporary cookie/body files and one short-lived API session for a
#   smoke user. Does not mutate article data or run worker jobs.

set -euo pipefail

ENV="${1:?必须提供环境名，例如 staging 或 prod}"

if [[ "$ENV" != "staging" && "$ENV" != "prod" ]]; then
    echo "❌ 错误：ENV 必须是 staging 或 prod，收到：$ENV"
    exit 1
fi

# Resolve the repo-local .env so smoke tests can run from CI SSH or manual shells.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

set -a; source "$REPO_ROOT/.env"; set +a

PROJECT="myrss-${ENV}"
API_CONTAINER="${PROJECT}-ai-reader-api-1"
WORKER_CONTAINER="${PROJECT}-ai-reader-worker-1"
READER_CONTAINER="${PROJECT}-reader-web-1"
MINIFLUX_CONTAINER="${PROJECT}-miniflux-1"
AUTHELIA_CONTAINER="${PROJECT}-authelia-1"
POSTGRES_CONTAINER="${PROJECT}-postgres-1"
EDGE_CONTAINER="myrss-edge-caddy-1"

if [[ "$ENV" == "staging" ]]; then
    PUBLIC_URL="https://staging-ai-reader.${DOMAIN}"
else
    PUBLIC_URL="https://ai-reader.${DOMAIN}"
fi

# Auth boundary differs by environment: staging is a public demo where anonymous
# requests resolve to a shared demo user (articles 200, admin still role-gated to
# 403); prod stays fail-closed (401 for any unauthenticated API call).
if [[ "$ENV" == "staging" ]]; then
    EXPECT_ANON_ARTICLES=200
    EXPECT_ANON_ADMIN=403
else
    EXPECT_ANON_ARTICLES=401
    EXPECT_ANON_ADMIN=401
fi

echo "🔎 Smoke test：$ENV"

# Container checks catch failed Compose recreates before HTTP probes hide the cause.
require_running() {
    local container="$1"
    local running
    running="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)"
    if [[ "$running" != "true" ]]; then
        echo "❌ 容器未运行：$container"
        exit 1
    fi
    echo "  ✅ $container running"
}

require_running "$API_CONTAINER"
require_running "$WORKER_CONTAINER"
require_running "$READER_CONTAINER"
require_running "$MINIFLUX_CONTAINER"
require_running "$AUTHELIA_CONTAINER"
require_running "$POSTGRES_CONTAINER"
require_running "$EDGE_CONTAINER"

if ! docker logs --tail 80 "$WORKER_CONTAINER" 2>&1 | grep -q "worker runtime started"; then
    echo "❌ worker 未输出启动日志：$WORKER_CONTAINER"
    exit 1
fi
echo "  ✅ worker startup log ok"

# Internal API probes distinguish service health from edge-routing failures.
docker exec \
    -e EXPECT_ANON_ARTICLES="$EXPECT_ANON_ARTICLES" \
    -e EXPECT_ANON_ADMIN="$EXPECT_ANON_ADMIN" \
    "$API_CONTAINER" python - <<'PY'
import json
import os
import urllib.error
import urllib.request


def require_json_ok(path: str) -> None:
    with urllib.request.urlopen(f"http://127.0.0.1:8000{path}", timeout=5) as response:
        body = response.read().decode()
    payload = json.loads(body)
    if payload.get("ok") is not True:
        raise SystemExit(f"{path} not ok")


def require_status(path: str, expected: int) -> None:
    request = urllib.request.Request(f"http://127.0.0.1:8000{path}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            code = response.status
    except urllib.error.HTTPError as error:
        code = error.code
    if code != expected:
        raise SystemExit(f"{path} returned {code}, expected {expected}")


require_json_ok("/healthz")
require_json_ok("/api/healthz")
require_status("/api/articles", int(os.environ["EXPECT_ANON_ARTICLES"]))
require_status("/api/admin/users", int(os.environ["EXPECT_ANON_ADMIN"]))
print("  ✅ internal api health and anonymous auth boundaries ok")
PY

# Public HTTP probes prove Caddy routes health and API paths to the expected services.
require_http_status() {
    local path="$1"
    local expected="$2"
    local body_file
    local code
    body_file="$(mktemp)"
    code="$(curl -sS -o "$body_file" -w "%{http_code}" --connect-timeout 10 "$PUBLIC_URL$path")"
    rm -f "$body_file"
    if [[ "$code" != "$expected" ]]; then
        echo "❌ $PUBLIC_URL$path returned HTTP $code, expected $expected"
        exit 1
    fi
    echo "  ✅ $path HTTP $expected"
}

require_http_status "/healthz" "200"
require_http_status "/api/healthz" "200"
require_http_status "/api/articles" "$EXPECT_ANON_ARTICLES"
require_http_status "/api/admin/users" "$EXPECT_ANON_ADMIN"

# Staging serves app page routes publicly (no Authelia gate). They can transiently
# 5xx while reader-web restarts, so retry until the app shell is served with 200.
require_staging_public_app() {
    local path="/?module=all&sort=default&lang=zh"
    local attempts=12
    local delay_seconds=2
    local attempt
    local body_file
    local code

    for attempt in $(seq 1 "$attempts"); do
        body_file="$(mktemp)"
        if ! code="$(curl -sS -o "$body_file" -w "%{http_code}" --connect-timeout 10 "$PUBLIC_URL$path")"; then
            code="000"
        fi

        if [[ "$code" == 200 ]] && grep -q "AI Reader" "$body_file"; then
            rm -f "$body_file"
            echo "  ✅ staging app route publicly served: HTTP 200"
            return
        fi

        rm -f "$body_file"
        if [[ "$attempt" -lt "$attempts" ]]; then
            sleep "$delay_seconds"
        fi
    done

    echo "❌ staging app route not publicly served (last HTTP $code)"
    exit 1
}

# The display-name session check proves FastAPI auth works without requiring admin secrets.
COOKIE_JAR="$(mktemp)"
LOGIN_BODY="$(mktemp)"
ADMIN_BODY="$(mktemp)"
trap 'rm -f "$COOKIE_JAR" "$LOGIN_BODY" "$ADMIN_BODY"' EXIT

LOGIN_CODE="$(
    curl -sS \
        -o "$LOGIN_BODY" \
        -c "$COOKIE_JAR" \
        -w "%{http_code}" \
        --connect-timeout 10 \
        -H "Content-Type: application/json" \
        -H "Origin: $PUBLIC_URL" \
        --data "{\"display_name\":\"smoke-${ENV}\"}" \
        "$PUBLIC_URL/api/auth/login"
)"
if [[ "$LOGIN_CODE" != "200" ]]; then
    echo "❌ smoke login returned HTTP $LOGIN_CODE"
    exit 1
fi

ADMIN_CODE="$(
    curl -sS \
        -o "$ADMIN_BODY" \
        -b "$COOKIE_JAR" \
        -w "%{http_code}" \
        --connect-timeout 10 \
        "$PUBLIC_URL/api/admin/users"
)"
if [[ "$ADMIN_CODE" != "403" ]]; then
    echo "❌ non-admin admin boundary returned HTTP $ADMIN_CODE, expected 403"
    exit 1
fi
echo "  ✅ logged-in non-admin admin boundary HTTP 403"

# Staging publicly serves the app shell (the demo session bootstraps without login).
if [[ "$ENV" == "staging" ]]; then
    LANDING_BODY="$(curl -fsSL --connect-timeout 10 "$PUBLIC_URL/")"
    for text in "AI Reader" "正在验证会话" "阅读工作台"; do
        if [[ "$LANDING_BODY" != *"$text"* ]]; then
            echo "❌ staging app shell missing marker: $text"
            exit 1
        fi
    done
    echo "  ✅ staging public app shell ok"

    require_staging_public_app
fi

echo "✅ Smoke test passed：$ENV"
