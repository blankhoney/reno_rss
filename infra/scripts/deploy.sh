#!/usr/bin/env bash
# 部署脚本：部署指定环境（staging 或 prod）到当前服务器
#
# 用法：
#   bash infra/scripts/deploy.sh staging v1.2.3
#   bash infra/scripts/deploy.sh prod    v1.2.3
#
# 参数：
#   $1  ENV  — 环境名，必须是 staging 或 prod
#   $2  TAG  — 镜像 tag，例如 v1.2.3 或 sha-abc1234

set -euo pipefail

# shell 环境变量优先级高于 --env-file，清除可能被外部工具（如 pi agent）污染的变量
# 确保 docker compose 从 --env-file 读取真实值，而不是残留的占位符
unset MINIFLUX_API_KEY MINIFLUX_ADMIN_PASSWORD POSTGRES_SUPERUSER_PASSWORD \
      POSTGRES_MINIFLUX_PASSWORD POSTGRES_SCORING_PASSWORD SMTP_PASSWORD \
      MINIMAX_API_KEY MINIMAX_BASE_URL MINIMAX_MODEL LLM_TIMEOUT_SECONDS \
      READER_TENANT_ID READER_MINIFLUX_USER_ID WEB_SEARCH_PROVIDER WEB_SEARCH_API_KEY \
      DEMO_LANDING_ENABLED DEMO_USERNAME DEMO_PASSWORD DEMO_AUTHELIA_BASE_URL \
      DEMO_TARGET_URL DEMO_ALLOWED_ORIGIN AI_READER_CSRF_ALLOWED_ORIGINS \
      LLM_PROVIDER WORKER_CONCURRENCY EXTERNAL_CONTENT_PROVIDER

ENV="${1:?必须提供环境名，例如 staging 或 prod}"
TAG="${2:?必须提供镜像 tag，例如 v1.2.3}"
DEPLOY_IMAGE_REGISTRY="${IMAGE_REGISTRY:-}"
DEPLOY_AI_READER_WEB_IMAGE="${AI_READER_WEB_IMAGE:-}"
DEPLOY_AI_READER_API_IMAGE="${AI_READER_API_IMAGE:-}"
DEPLOY_AI_READER_WORKER_IMAGE="${AI_READER_WORKER_IMAGE:-}"
DEPLOY_LOCAL_BUILD="${LOCAL_BUILD:-}"

# 校验 ENV 参数，防止误操作
if [[ "$ENV" != "staging" && "$ENV" != "prod" ]]; then
    echo "❌ 错误：ENV 必须是 staging 或 prod，收到：$ENV"
    exit 1
fi

# 脚本所在目录（无论从哪里调用，路径都正确）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── Step 0：生成 Authelia 配置文件（envsubst 替换域名等变量）──
# 从 .env 加载变量，envsubst 把 ${DOMAIN} 替换为真实值。
# CI/CD 传入的镜像变量优先级高于 .env 中的空值或旧值。
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

run_prod_migration_backup() {
    if [[ "$ENV" != "prod" ]]; then
        echo "💾 $ENV 非生产环境：跳过迁移前备份 gate"
        return
    fi

    local backup_output
    local backup_dir
    local backup_path
    local backup_sha256_file

    echo "💾 prod 迁移前备份数据库..."
    if ! backup_output="$(cd "$REPO_ROOT" && "$SCRIPT_DIR/backup.sh" prod 2>&1)"; then
        echo "$backup_output"
        echo "❌ prod 数据库备份失败，停止迁移和部署"
        exit 1
    fi
    echo "$backup_output"

    backup_dir="$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_DIR=//p' | tail -n 1)"
    if [[ -z "$backup_dir" ]]; then
        echo "❌ 无法从 backup.sh 输出中解析 BACKUP_DIR，停止迁移"
        exit 1
    fi
    backup_sha256_file="$(printf '%s\n' "$backup_output" | sed -n 's/^BACKUP_SHA256_FILE=//p' | tail -n 1)"
    if [[ -z "$backup_sha256_file" ]]; then
        echo "❌ 无法从 backup.sh 输出中解析 BACKUP_SHA256_FILE，停止迁移"
        exit 1
    fi
    backup_path="$backup_dir"
    if [[ "$backup_path" != /* ]]; then
        backup_path="$REPO_ROOT/${backup_path#./}"
    fi
    if [[ "$backup_sha256_file" != /* ]]; then
        backup_sha256_file="$REPO_ROOT/${backup_sha256_file#./}"
    fi
    if [[ ! -f "$backup_sha256_file" ]]; then
        echo "❌ 备份校验文件不存在：$backup_sha256_file"
        exit 1
    fi

    echo "   backup artifact: $backup_path"
    echo "   sha256:"
    sed 's/^/     /' "$backup_sha256_file"

    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        {
            echo "### Production database backup"
            echo ""
            echo "- Artifact: \`$backup_path\`"
            echo ""
            echo "\`\`\`"
            cat "$backup_sha256_file"
            echo "\`\`\`"
        } >> "$GITHUB_STEP_SUMMARY"
    fi
}

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

mkdir -p "$AUTHELIA_ASSETS_DIR"
if [[ "$ENV" == "staging" ]]; then
    write_authelia_demo_locale_overrides
    echo "📝 Authelia staging demo locale overrides 已生成"
fi

envsubst < "$REPO_ROOT/infra/authelia/configuration.yml.tmpl" \
    > "$REPO_ROOT/infra/authelia/configuration.yml"
echo "📝 Authelia 配置已生成"

# ── Step 1：确保共享 edge 网络存在 ──────────────────────────
# edge 网络由 docker-compose.edge.yml 创建，prod/staging 共用
# 如果已经存在，docker network create 会报错，用 || true 忽略
docker network create myrss-app 2>/dev/null || true

# ── Step 2：启动/更新唯一的边缘入口（Caddy）────────────────
# -p myrss-edge：project name，确保全局只有一个 Caddy 实例
# --remove-orphans：移除上次启动后被删除的服务容器
echo "📡 更新 edge 入口（Caddy）..."
IMAGE_TAG="$TAG" docker compose \
    -p "myrss-edge" \
    --env-file "$REPO_ROOT/.env" \
    -f "$REPO_ROOT/infra/compose/docker-compose.edge.yml" \
    up -d --force-recreate --remove-orphans

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

# ── Step 3：启动/更新环境后端服务 ───────────────────────────
# 叠加 base.yml + <env>.yml，ENV 参数决定使用哪套别名
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

# PROD_MIGRATION_BACKUP_GATE
run_prod_migration_backup

# API_MIGRATION_READY_GATE
wait_for_api_migration_ready

echo "🗄️  应用 $ENV API 数据库迁移..."
IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" exec -T ai-reader-api alembic upgrade head

echo "🔁 重建 $ENV Authelia 以加载生成配置..."
IMAGE_TAG="$TAG" "${BACKEND_COMPOSE[@]}" \
    up -d --force-recreate --no-deps authelia

echo "✅ 部署完成：$ENV @ $TAG"
