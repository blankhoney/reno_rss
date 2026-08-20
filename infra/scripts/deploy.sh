#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Purpose:
#   Deploy the AI Reader stack for staging or production on the current VPS.
#
# Usage:
#   bash infra/scripts/deploy.sh staging v1.2.3
#   bash infra/scripts/deploy.sh prod    v1.2.3
#
# Arguments:
#   $1  ENV  Environment name; must be staging or prod.
#   $2  TAG  Image tag, for example v1.2.3 or sha-abc1234.
#
# Environment:
#   Reads .env from the repository root. CI may override IMAGE_REGISTRY,
#   AI_READER_*_IMAGE, and LOCAL_BUILD before .env is loaded.
#
# Exit codes:
#   0 when Caddy, backend services, migrations, and Authelia refresh complete.
#   Non-zero on invalid ENV, missing env values, failed backup/readiness gates,
#   failed Compose commands, failed Caddy validation, or failed migrations.
#
# Side effects:
#   Rewrites generated Authelia config/assets, creates the shared Docker network,
#   pulls/builds images, recreates services, runs Alembic migrations, and may write
#   a production database backup before prod migrations.

set -euo pipefail

# Invariant: deployment must not inherit placeholder secrets from an invoking agent shell.
unset MINIFLUX_API_KEY MINIFLUX_ADMIN_PASSWORD POSTGRES_SUPERUSER_PASSWORD \
      POSTGRES_MINIFLUX_PASSWORD POSTGRES_SCORING_PASSWORD SMTP_PASSWORD \
      MINIMAX_API_KEY MINIMAX_BASE_URL MINIMAX_MODEL LLM_TIMEOUT_SECONDS \
      MINIMAX_TEMPERATURE MINIMAX_TOP_P MINIMAX_MAX_COMPLETION_TOKENS \
      MINIMAX_REASONING_SPLIT MINIMAX_THINKING_TYPE \
      READER_TENANT_ID READER_MINIFLUX_USER_ID WEB_SEARCH_PROVIDER WEB_SEARCH_API_KEY \
      DEMO_LANDING_ENABLED DEMO_USERNAME DEMO_PASSWORD DEMO_AUTHELIA_BASE_URL \
      DEMO_TARGET_URL DEMO_ALLOWED_ORIGIN AI_READER_CSRF_ALLOWED_ORIGINS \
      LLM_PROVIDER WORKER_CONCURRENCY EXTERNAL_CONTENT_PROVIDER \
      SCHEDULE_SCORE_DAILY_ARTICLE_CAP SCHEDULER_ENABLED

ENV="${1:?必须提供环境名，例如 staging 或 prod}"
TAG="${2:?必须提供镜像 tag，例如 v1.2.3}"
DEPLOY_IMAGE_REGISTRY="${IMAGE_REGISTRY:-}"
DEPLOY_AI_READER_WEB_IMAGE="${AI_READER_WEB_IMAGE:-}"
DEPLOY_AI_READER_API_IMAGE="${AI_READER_API_IMAGE:-}"
DEPLOY_AI_READER_WORKER_IMAGE="${AI_READER_WORKER_IMAGE:-}"
DEPLOY_LOCAL_BUILD="${LOCAL_BUILD:-}"

# Fail before any side effect if the requested environment is not explicitly supported.
if [[ "$ENV" != "staging" && "$ENV" != "prod" ]]; then
    echo "❌ 错误：ENV 必须是 staging 或 prod，收到：$ENV"
    exit 1
fi

# Resolve paths from the script location so deploys behave the same from CI and SSH shells.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load server-local configuration after preserving CI image overrides.
set -a; source "$REPO_ROOT/.env"; set +a

IMAGE_REGISTRY="${DEPLOY_IMAGE_REGISTRY:-${IMAGE_REGISTRY:-}}"
AI_READER_WEB_IMAGE="${DEPLOY_AI_READER_WEB_IMAGE:-${AI_READER_WEB_IMAGE:-}}"
AI_READER_API_IMAGE="${DEPLOY_AI_READER_API_IMAGE:-${AI_READER_API_IMAGE:-}}"
AI_READER_WORKER_IMAGE="${DEPLOY_AI_READER_WORKER_IMAGE:-${AI_READER_WORKER_IMAGE:-}}"
LOCAL_BUILD="${DEPLOY_LOCAL_BUILD:-${LOCAL_BUILD:-0}}"

IMAGE_REGISTRY="${IMAGE_REGISTRY%/}"
USE_REMOTE_IMAGES=0
if [[ -n "$IMAGE_REGISTRY" && "$LOCAL_BUILD" != "1" ]]; then
    USE_REMOTE_IMAGES=1
    export AI_READER_WEB_IMAGE="${AI_READER_WEB_IMAGE:-${IMAGE_REGISTRY}/ai-reader-web:${TAG}}"
    export AI_READER_API_IMAGE="${AI_READER_API_IMAGE:-${IMAGE_REGISTRY}/ai-reader-api:${TAG}}"
    export AI_READER_WORKER_IMAGE="${AI_READER_WORKER_IMAGE:-${IMAGE_REGISTRY}/ai-reader-worker:${TAG}}"
else
    export AI_READER_WEB_IMAGE="${AI_READER_WEB_IMAGE:-myrss-ai-reader-web:${TAG}}"
    export AI_READER_API_IMAGE="${AI_READER_API_IMAGE:-myrss-ai-reader-api:${TAG}}"
    export AI_READER_WORKER_IMAGE="${AI_READER_WORKER_IMAGE:-myrss-ai-reader-worker:${TAG}}"
fi

AUTHELIA_ASSETS_DIR="$REPO_ROOT/infra/authelia/assets"
AUTHELIA_LOCALES_DIR="$AUTHELIA_ASSETS_DIR/locales"
AUTHELIA_LOCALES=(en zh-CN zh-HK zh-TW zh-SG)

json_escape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '%s' "$value"
}

# Staging keeps Authelia labels explicit so public demo credentials are visible before 2FA.
write_authelia_demo_locale_overrides() {
    : "${DEMO_USERNAME:?staging 部署必须设置 DEMO_USERNAME}"
    : "${DEMO_PASSWORD:?staging 部署必须设置 DEMO_PASSWORD}"

    local demo_notice="Demo only for staging-ai-reader.${DOMAIN}"
    local username_label="Username - ${demo_notice}: ${DEMO_USERNAME}"
    local password_label="Password - ${demo_notice}: ${DEMO_PASSWORD}"
    local sign_in_label="Sign in - ${demo_notice}"
    local locale locale_dir

    for locale in "${AUTHELIA_LOCALES[@]}"; do
        locale_dir="$AUTHELIA_LOCALES_DIR/$locale"
        mkdir -p "$locale_dir"
        cat > "$locale_dir/portal.json" <<EOF
{
  "Username": "$(json_escape "$username_label")",
  "Password": "$(json_escape "$password_label")",
  "Sign in": "$(json_escape "$sign_in_label")"
}
EOF
    done
}

# Production activation consumes the single backup created and verified by the
# outer trusted transaction before any edge mutation or image pull.  This script
# revalidates the immutable evidence instead of creating a collision-prone second
# backup. Direct production invocation without trusted evidence fails closed.
run_prod_migration_backup() {
    if [[ "$ENV" != "prod" ]]; then
        echo "💾 $ENV 非生产环境：跳过迁移前备份 gate"
        return
    fi

    local evidence_file="${TRUSTED_PRODUCTION_BACKUP_EVIDENCE:-}"
    local workflow_operation="${TRUSTED_DEPLOY_OPERATION_SHA:-}"
    local backup_dir
    local backup_sha256_file
    local expected_checksum_digest
    local actual_checksum_digest

    [[ "$evidence_file" == /* && -f "$evidence_file" && ! -L "$evidence_file" ]] || {
        echo "❌ production deployment requires safe trusted backup evidence" >&2
        exit 1
    }
    [[ "$workflow_operation" =~ ^[0-9a-f]{40}$ ]] || {
        echo "❌ trusted deployment operation SHA is invalid" >&2
        exit 1
    }
    [[ "$(stat -c '%a:%u' "$evidence_file")" == "600:$(id -u)" ]] || {
        echo "❌ trusted backup evidence ownership or mode is unsafe" >&2
        exit 1
    }
    mapfile -d '' evidence_fields < <(python3 - "$evidence_file" "$workflow_operation" <<'PY'
import json,re,sys
path,operation=sys.argv[1:]
with open(path,encoding="utf-8") as source:item=json.load(source)
keys={"contractVersion","workflowOperationSha","environment","backupDir","checksumFile","checksumDigest"}
if type(item)is not dict or set(item)!=keys:raise SystemExit("trusted backup evidence schema mismatch")
if item["contractVersion"]!="trusted-production-backup/v1" or item["environment"]!="prod" or item["workflowOperationSha"]!=operation:raise SystemExit("trusted backup evidence identity mismatch")
for key in ("backupDir","checksumFile"):
 if type(item[key])is not str or not item[key].startswith("/") or "\n" in item[key]:raise SystemExit(f"trusted backup evidence {key} is invalid")
if type(item["checksumDigest"])is not str or re.fullmatch(r"sha256:[0-9a-f]{64}",item["checksumDigest"])is None:raise SystemExit("trusted backup evidence checksum digest is invalid")
for value in (item["backupDir"],item["checksumFile"],item["checksumDigest"]):sys.stdout.write(value+"\0")
PY
    )
    (( ${#evidence_fields[@]} == 3 )) || {
        echo "❌ trusted backup evidence validation failed" >&2
        exit 1
    }
    backup_dir="${evidence_fields[0]}"
    backup_sha256_file="${evidence_fields[1]}"
    expected_checksum_digest="${evidence_fields[2]#sha256:}"
    [[ -d "$backup_dir" && ! -L "$backup_dir" && -f "$backup_sha256_file" && ! -L "$backup_sha256_file" ]] || {
        echo "❌ trusted backup artifact is missing or unsafe" >&2
        exit 1
    }
    [[ "$(realpath -e "$backup_dir")" == "$(realpath -e "$REPO_ROOT/backup")/"* ]] || {
        echo "❌ trusted backup directory escaped the repository backup root" >&2
        exit 1
    }
    [[ "$(realpath -e "$backup_sha256_file")" == "$(realpath -e "$backup_dir")/"* ]] || {
        echo "❌ trusted backup checksum escaped its backup directory" >&2
        exit 1
    }
    read -r actual_checksum_digest _ < <(sha256sum "$backup_sha256_file")
    [[ "$actual_checksum_digest" == "$expected_checksum_digest" ]] || {
        echo "❌ trusted backup checksum evidence changed after verification" >&2
        exit 1
    }
    if ! (cd "$backup_dir" && sha256sum -c "$backup_sha256_file"); then
        echo "❌ prod 数据库备份校验失败，停止部署"
        exit 1
    fi

    echo "   trusted backup artifact: $backup_dir"
    echo "   sha256:"
    sed 's/^/     /' "$backup_sha256_file"
}

# Alembic must run only after the API container can connect to the target database.
wait_for_api_migration_ready() {
    local max_attempts="${MIGRATION_READY_MAX_ATTEMPTS:-12}"
    local sleep_seconds="${MIGRATION_READY_SLEEP_SECONDS:-5}"
    local attempt

    echo "⏳ 等待 $ENV API/DB 可执行迁移..."
    for attempt in $(seq 1 "$max_attempts"); do
        if IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" exec -T ai-reader-api alembic current >/dev/null 2>&1; then
            echo "  ✅ migration context ready"
            return
        fi
        echo "  等待 migration context：attempt $attempt/$max_attempts"
        sleep "$sleep_seconds"
    done

    echo "❌ API/DB 在限定时间内未就绪，停止迁移"
    exit 1
}

echo "🚀 开始部署：ENV=$ENV  TAG=$TAG"
echo "   仓库根目录：$REPO_ROOT"
if [[ "$USE_REMOTE_IMAGES" == "1" ]]; then
    echo "   镜像模式：remote ($IMAGE_REGISTRY)"
else
    echo "   镜像模式：local build"
fi

# These named markers are asserted by check-deploy-migrations.sh.
# PROD_MIGRATION_BACKUP_GATE
# Complete the production backup before starting any new edge/backend revision.
# Staging remains an explicit no-op inside the gate.
run_prod_migration_backup

# Regenerate edge-auth assets before Caddy validates its mounted configuration.
mkdir -p "$AUTHELIA_ASSETS_DIR"
if [[ "$ENV" == "staging" ]]; then
    write_authelia_demo_locale_overrides
    echo "📝 Authelia staging demo locale overrides 已生成"
fi

envsubst < "$REPO_ROOT/infra/authelia/configuration.yml.tmpl" \
    > "$REPO_ROOT/infra/authelia/configuration.yml"
echo "📝 Authelia 配置已生成"

# The app network is shared by staging/prod backends and the single edge Caddy instance.
docker network create myrss-app 2>/dev/null || true

# Recreate the single edge entrypoint before backend smoke checks depend on routing.
echo "📡 更新 edge 入口（Caddy）..."
IMAGE_TAG="$TAG" docker compose \
    -p "myrss-edge" \
    --env-file "$REPO_ROOT/.env" \
    -f "$REPO_ROOT/infra/compose/docker-compose.edge.yml" \
    up -d --remove-orphans

# Compose declares both production edge networks, and this recovery closes any
# attachment drift caused by an interrupted recreate without touching Blog
# containers or creating a competing network lifecycle.
bash "$REPO_ROOT/infra/deploy/ensure-shared-edge.sh"

echo "🔁 校验并重载 Caddy 配置..."
docker compose \
    -p "myrss-edge" \
    --env-file "$REPO_ROOT/.env" \
    -f "$REPO_ROOT/infra/compose/docker-compose.edge.yml" \
    exec -T caddy caddy validate --config /etc/caddy/Caddyfile
docker compose \
    -p "myrss-edge" \
    --env-file "$REPO_ROOT/.env" \
    -f "$REPO_ROOT/infra/compose/docker-compose.edge.yml" \
    exec -T caddy caddy reload --config /etc/caddy/Caddyfile

# Build the environment-specific backend stack from base plus the selected overlay.
echo "🔧 更新 $ENV 后端服务..."
BACKEND_COMPOSE=(
    docker compose
    --env-file "$REPO_ROOT/.env" \
    -p "myrss-${ENV}" \
    -f "$REPO_ROOT/infra/compose/docker-compose.base.yml" \
    -f "$REPO_ROOT/infra/compose/docker-compose.${ENV}.yml"
)

if [[ "$USE_REMOTE_IMAGES" == "1" ]]; then
    echo "📦 拉取 $ENV 业务镜像..."
    IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" pull reader-web ai-reader-api ai-reader-worker
    IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" up -d --no-build --remove-orphans
else
    IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" up -d --build --remove-orphans
fi

# API_MIGRATION_READY_GATE
wait_for_api_migration_ready

# Apply schema changes before recreating Authelia, so smoke checks never see a runtime ahead of its schema.
echo "🗄️  应用 $ENV API 数据库迁移..."
IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" exec -T ai-reader-api alembic upgrade head

echo "🔁 重建 $ENV Authelia 以加载生成配置..."
IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" \
    up -d --force-recreate --no-deps authelia

echo "✅ 部署完成：$ENV @ $TAG"
