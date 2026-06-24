#!/usr/bin/env bash
# Lightweight post-deploy smoke test for staging/prod.

set -euo pipefail

ENV="${1:?必须提供环境名，例如 staging 或 prod}"

if [[ "$ENV" != "staging" && "$ENV" != "prod" ]]; then
    echo "❌ 错误：ENV 必须是 staging 或 prod，收到：$ENV"
    exit 1
fi

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

echo "🔎 Smoke test：$ENV"

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

docker exec "$API_CONTAINER" python - <<'PY'
import json
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
        urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        if error.code != expected:
            raise SystemExit(f"{path} returned {error.code}, expected {expected}") from error
    else:
        raise SystemExit(f"{path} returned success, expected {expected}")


require_json_ok("/healthz")
require_json_ok("/api/healthz")
require_status("/api/articles", 401)
require_status("/api/admin/users", 401)
print("  ✅ internal api health and anonymous auth boundaries ok")
PY

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
require_http_status "/api/articles" "401"
require_http_status "/api/admin/users" "401"

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

if [[ "$ENV" == "staging" ]]; then
    LANDING_BODY="$(curl -fsSL --connect-timeout 10 "$PUBLIC_URL/")"
    for text in "AI Reader" "以游客身份进入" "GitHub"; do
        if [[ "$LANDING_BODY" != *"$text"* ]]; then
            echo "❌ staging demo landing missing marker: $text"
            exit 1
        fi
    done
    echo "  ✅ staging demo landing ok"

    PROTECTED_BODY_FILE="$(mktemp)"
    PROTECTED_CODE="$(curl -sS -o "$PROTECTED_BODY_FILE" -w "%{http_code}" --connect-timeout 10 "$PUBLIC_URL/?module=all&sort=default&lang=zh")"
    if [[ ! "$PROTECTED_CODE" =~ ^(2|3)[0-9][0-9]$ ]]; then
        echo "❌ staging protected route returned HTTP $PROTECTED_CODE"
        rm -f "$PROTECTED_BODY_FILE"
        exit 1
    fi
    if [[ "$PROTECTED_CODE" == 200 ]] && grep -q "阅读工作台" "$PROTECTED_BODY_FILE"; then
        echo "❌ staging protected route exposed business UI without auth"
        rm -f "$PROTECTED_BODY_FILE"
        exit 1
    fi
    rm -f "$PROTECTED_BODY_FILE"
    echo "  ✅ staging protected route boundary ok: HTTP $PROTECTED_CODE"
fi

echo "✅ Smoke test passed：$ENV"
