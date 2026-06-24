#!/usr/bin/env bash
# 备份脚本：对 miniflux 和 scoring 数据库做逻辑备份
#
# 用法：
#   bash infra/scripts/backup.sh
#
# 备份文件保存在：./backup/YYYY-MM-DD_HH-MM-SS/
# 格式：pg_dump -Fc（自定义压缩格式，用 pg_restore 恢复）
# 同时生成 sha256 校验和文件，用于验证备份完整性

set -euo pipefail

# PG 容器名（prod 环境）
PG_CONTAINER="myrss-prod-postgres-1"
BACKUP_DIR="./backup/$(date +%Y-%m-%d_%H-%M-%S)"

mkdir -p "$BACKUP_DIR"
BACKUP_PATH="$(cd "$BACKUP_DIR" && pwd)"

echo "💾 开始备份到 $BACKUP_PATH ..."

# 备份 miniflux 数据库
docker exec "$PG_CONTAINER" \
    pg_dump -U postgres -Fc miniflux \
    > "$BACKUP_PATH/miniflux.dump"
echo "  ✅ miniflux.dump"

# 备份 scoring 数据库
docker exec "$PG_CONTAINER" \
    pg_dump -U postgres -Fc scoring \
    > "$BACKUP_PATH/scoring.dump"
echo "  ✅ scoring.dump"

# 生成校验和（用于验证文件未损坏）
sha256sum "$BACKUP_PATH/miniflux.dump" "$BACKUP_PATH/scoring.dump" \
    > "$BACKUP_PATH/checksums.txt"
echo "  ✅ checksums.txt"

echo "BACKUP_DIR=$BACKUP_PATH"
echo "BACKUP_SHA256_FILE=$BACKUP_PATH/checksums.txt"
echo "✅ 备份完成：$BACKUP_PATH"
echo "   文件大小："
du -sh "$BACKUP_PATH"/*

# 清理 7 天前的旧备份（按目录修改时间判断）
echo "🧹 清理 7 天前的旧备份..."
find ./backup -maxdepth 1 -mindepth 1 -type d -mtime +7 -print -exec rm -rf {} +
echo "✅ 清理完成，当前保留备份："
ls ./backup/
