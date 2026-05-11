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

echo "💾 开始备份到 $BACKUP_DIR ..."

# 备份 miniflux 数据库
docker exec "$PG_CONTAINER" \
    pg_dump -U postgres -Fc miniflux \
    > "$BACKUP_DIR/miniflux.dump"
echo "  ✅ miniflux.dump"

# 备份 scoring 数据库
docker exec "$PG_CONTAINER" \
    pg_dump -U postgres -Fc scoring \
    > "$BACKUP_DIR/scoring.dump"
echo "  ✅ scoring.dump"

# 生成校验和（用于验证文件未损坏）
sha256sum "$BACKUP_DIR/miniflux.dump" "$BACKUP_DIR/scoring.dump" \
    > "$BACKUP_DIR/checksums.txt"
echo "  ✅ checksums.txt"

echo "✅ 备份完成：$BACKUP_DIR"
echo "   文件大小："
du -sh "$BACKUP_DIR"/*
