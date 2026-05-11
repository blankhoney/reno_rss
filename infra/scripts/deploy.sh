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
