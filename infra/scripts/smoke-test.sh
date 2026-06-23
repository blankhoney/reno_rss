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
READER_CONTAINER="${PROJECT}-reader-web-1"
SCORER_CONTAINER="${PROJECT}-scorer-worker-1"
MINIFLUX_CONTAINER="${PROJECT}-miniflux-1"
AUTHELIA_CONTAINER="${PROJECT}-authelia-1"
POSTGRES_CONTAINER="${PROJECT}-postgres-1"
EDGE_CONTAINER="myrss-edge-caddy-1"

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

require_running "$READER_CONTAINER"
require_running "$SCORER_CONTAINER"
require_running "$MINIFLUX_CONTAINER"
require_running "$AUTHELIA_CONTAINER"
require_running "$POSTGRES_CONTAINER"
require_running "$EDGE_CONTAINER"

docker exec "$SCORER_CONTAINER" python - <<'PY'
import json
import urllib.request

body = urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=5).read().decode()
payload = json.loads(body)
if payload.get("ok") is not True:
    raise SystemExit(f"scorer healthz not ok: {body}")
print("  ✅ scorer healthz ok")
PY

docker exec "$READER_CONTAINER" node - <<'NODE'
const base = "http://127.0.0.1:3000";

async function requireOk(path) {
  const response = await fetch(`${base}${path}`);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response;
}

const listResponse = await requireOk("/api/articles?module=all&sort=default");
const list = await listResponse.json();
if (!Array.isArray(list.articles)) {
  throw new Error("/api/articles did not return an articles array");
}

const home = await (await requireOk("/?module=all&sort=default&lang=zh")).text();
for (const text of ["阅读工作台", "重评前", "排序"]) {
  if (!home.includes(text)) throw new Error(`home page missing ${text}`);
}

if (list.articles.length > 0) {
  const id = list.articles[0].id;
  const article = await (await requireOk(`/read/${id}?module=all&sort=default&lang=zh`)).text();
  if (!article.includes("返回工作台") || !article.includes("文章助手")) {
    throw new Error(`/read/${id} missing focus reader markers`);
  }
  console.log(`  ✅ reader API/page ok, sample article=${id}`);
} else {
  console.log("  ⚠️ reader API/page ok, but no sample articles available");
}
NODE

if [[ "$ENV" == "staging" ]]; then
    PUBLIC_URL="https://staging-ai-reader.${DOMAIN}"
else
    PUBLIC_URL="https://ai-reader.${DOMAIN}"
fi

if [[ "$ENV" == "staging" ]]; then
    LANDING_BODY="$(curl -fsSL --connect-timeout 10 "$PUBLIC_URL/")"
    for text in "AI Reader" "以游客身份进入" "GitHub"; do
        if [[ "$LANDING_BODY" != *"$text"* ]]; then
            echo "❌ staging demo landing missing marker: $text"
            exit 1
        fi
    done
    echo "  ✅ staging demo landing ok"

    PROTECTED_BODY_FILE="/tmp/myrss-smoke-protected-body.txt"
    PROTECTED_CODE="$(curl -sS -o "$PROTECTED_BODY_FILE" -w "%{http_code}" --connect-timeout 10 "$PUBLIC_URL/?module=all&sort=default&lang=zh")"
    if [[ ! "$PROTECTED_CODE" =~ ^(2|3)[0-9][0-9]$ ]]; then
        echo "❌ staging protected route returned HTTP $PROTECTED_CODE"
        exit 1
    fi
    if [[ "$PROTECTED_CODE" == 200 ]] && grep -q "阅读工作台" "$PROTECTED_BODY_FILE"; then
        echo "❌ staging protected route exposed business UI without auth"
        exit 1
    fi
    echo "  ✅ staging protected route boundary ok: HTTP $PROTECTED_CODE"
fi

HTTP_CODE="$(curl -sS -o /tmp/myrss-smoke-headers.txt -w "%{http_code}" -I --connect-timeout 10 "$PUBLIC_URL")"
if [[ ! "$HTTP_CODE" =~ ^(2|3)[0-9][0-9]$ ]]; then
    echo "❌ 公网入口异常：$PUBLIC_URL HTTP $HTTP_CODE"
    tail -40 /tmp/myrss-smoke-headers.txt || true
    exit 1
fi

echo "  ✅ public entry ok: $PUBLIC_URL HTTP $HTTP_CODE"
echo "✅ Smoke test passed：$ENV"
