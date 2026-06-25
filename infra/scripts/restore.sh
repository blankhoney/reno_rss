#!/usr/bin/env bash
# 恢复脚本：从备份目录恢复 miniflux 和 scoring 数据库
#
# 用法：
#   bash infra/scripts/restore.sh ./backup/2026-05-11_12-00-00
#
# ⚠️  警告：恢复操作会覆盖现有数据库内容！
# ⚠️  恢复前会先停止 miniflux、API 和 worker，防止写冲突

set -euo pipefail

BACKUP_DIR="${1:?必须提供备份目录路径，例如 ./backup/2026-05-11_12-00-00}"
PG_CONTAINER="myrss-prod-postgres-1"

# 确认备份目录存在
if [[ ! -d "$BACKUP_DIR" ]]; then
    echo "❌ 备份目录不存在：$BACKUP_DIR"
    exit 1
fi

# 验证校验和
echo "🔍 验证备份文件完整性..."
sha256sum --check "$BACKUP_DIR/checksums.txt"
echo "  ✅ 校验和通过"

echo "⚠️  即将恢复数据库，这会覆盖现有数据！"
read -r -p "确认继续？输入 yes 继续：" CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    echo "已取消"
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 停止依赖数据库的服务（防止恢复期间有写入）
echo "⏸️  停止 miniflux、AI Reader API 和 worker..."
docker compose -p "myrss-prod" \
    -f "$REPO_ROOT/infra/compose/docker-compose.base.yml" \
    -f "$REPO_ROOT/infra/compose/docker-compose.prod.yml" \
    stop miniflux ai-reader-api ai-reader-worker

# 恢复 miniflux 数据库
echo "📥 恢复 miniflux..."
docker exec -i "$PG_CONTAINER" \
    pg_restore -U postgres -d miniflux --clean --if-exists \
    < "$BACKUP_DIR/miniflux.dump"
echo "  ✅ miniflux 恢复完成"

# 恢复 scoring 数据库
echo "📥 恢复 scoring..."
docker exec -i "$PG_CONTAINER" \
    pg_restore -U postgres -d scoring --clean --if-exists \
    < "$BACKUP_DIR/scoring.dump"
echo "  ✅ scoring 恢复完成"

# 重新启动服务
echo "▶️  重启服务..."
docker compose -p "myrss-prod" \
    -f "$REPO_ROOT/infra/compose/docker-compose.base.yml" \
    -f "$REPO_ROOT/infra/compose/docker-compose.prod.yml" \
    start miniflux ai-reader-api ai-reader-worker

echo "✅ 恢复完成，请验证服务是否正常运行"
