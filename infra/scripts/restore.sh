#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Purpose:
#   Restore production Miniflux and scoring databases from a backup directory.
#
# Usage:
#   bash infra/scripts/restore.sh ./backup/2026-05-11_12-00-00
#
# Arguments:
#   $1  Backup directory containing miniflux.dump, scoring.dump, and checksums.txt.
#
# Environment:
#   Reads production Compose files from the repository. Uses the fixed production
#   PostgreSQL container name from the myrss-prod Compose convention.
#
# Exit codes:
#   0 when checksums pass, both databases restore, and services restart.
#   Non-zero on missing backup directory, checksum mismatch, declined confirmation,
#   Docker/pg_restore failures, or service restart failures.
#
# Side effects:
#   Destructive: stops production Miniflux/API/worker, overwrites both databases,
#   then restarts those services.

set -euo pipefail

BACKUP_DIR="${1:?必须提供备份目录路径，例如 ./backup/2026-05-11_12-00-00}"
PG_CONTAINER="myrss-prod-postgres-1"

# Refuse to proceed unless the backup directory and checksums are present and valid.
if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "❌ 备份目录不存在：$BACKUP_DIR"
    exit 1
fi

# 验证校验和
echo "🔍 验证备份文件完整性..."
sha256sum --check "$BACKUP_DIR/checksums.txt"
echo "  ✅ 校验和通过"

# Human confirmation is required because pg_restore --clean replaces live data.
echo "⚠️  即将恢复数据库，这会覆盖现有数据！"
read -r -p "确认继续？输入 yes 继续：" CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    echo "已取消"
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Stop database writers to avoid mixed old/new state during destructive restore.
echo "⏸️  停止 miniflux、AI Reader API 和 worker..."
docker compose -p "myrss-prod" \
    -f "$REPO_ROOT/infra/compose/docker-compose.base.yml" \
    -f "$REPO_ROOT/infra/compose/docker-compose.prod.yml" \
    stop miniflux ai-reader-api ai-reader-worker

# Restore both logical dumps before bringing writers back online.
echo "📥 恢复 miniflux..."
docker exec -i "$PG_CONTAINER" \
    pg_restore -U postgres -d miniflux --clean --if-exists \
    < "$BACKUP_DIR/miniflux.dump"
echo "  ✅ miniflux 恢复完成"

echo "📥 恢复 scoring..."
docker exec -i "$PG_CONTAINER" \
    pg_restore -U postgres -d scoring --clean --if-exists \
    < "$BACKUP_DIR/scoring.dump"
echo "  ✅ scoring 恢复完成"

# Restart only the services paused for database consistency.
echo "▶️  重启服务..."
docker compose -p "myrss-prod" \
    -f "$REPO_ROOT/infra/compose/docker-compose.base.yml" \
    -f "$REPO_ROOT/infra/compose/docker-compose.prod.yml" \
    start miniflux ai-reader-api ai-reader-worker

echo "✅ 恢复完成，请验证服务是否正常运行"
