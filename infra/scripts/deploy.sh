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
      DIGEST_MIN_SCORE DIGEST_MAX_ITEMS READER_TENANT_ID READER_MINIFLUX_USER_ID \
      WEB_SEARCH_PROVIDER WEB_SEARCH_API_KEY

ENV="${1:?必须提供环境名，例如 staging 或 prod}"
TAG="${2:?必须提供镜像 tag，例如 v1.2.3}"

# 校验 ENV 参数，防止误操作
if [[ "$ENV" != "staging" && "$ENV" != "prod" ]]; then
    echo "❌ 错误：ENV 必须是 staging 或 prod，收到：$ENV"
    exit 1
fi

# 脚本所在目录（无论从哪里调用，路径都正确）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "🚀 开始部署：ENV=$ENV  TAG=$TAG"
echo "   仓库根目录：$REPO_ROOT"

# ── Step 0：生成 Authelia 配置文件（envsubst 替换域名等变量）──
# 从 .env 加载变量，envsubst 把 ${DOMAIN} 替换为真实值
set -a; source "$REPO_ROOT/.env"; set +a
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
    up -d --remove-orphans

# ── Step 3：启动/更新环境后端服务 ───────────────────────────
# 叠加 base.yml + <env>.yml，ENV 参数决定使用哪套别名
echo "🔧 更新 $ENV 后端服务..."
IMAGE_TAG="$TAG" docker compose \
    -p "myrss-${ENV}" \
    -f "$REPO_ROOT/infra/compose/docker-compose.base.yml" \
    -f "$REPO_ROOT/infra/compose/docker-compose.${ENV}.yml" \
    up -d --remove-orphans

echo "✅ 部署完成：$ENV @ $TAG"
