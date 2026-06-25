#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Purpose:
#   Create restorable logical backups for the production Miniflux and scoring databases.
#
# Usage:
#   bash infra/scripts/backup.sh
#
# Arguments:
#   None.
#
# Environment:
#   Reads the running production PostgreSQL container name from the fixed
#   myrss-prod Compose convention.
#
# Exit codes:
#   0 when both dumps and their checksum file are written.
#   Non-zero on any Docker, pg_dump, checksum, or cleanup failure.
#
# Side effects:
#   Writes ./backup/YYYY-MM-DD_HH-MM-SS/*.dump and checksums.txt, then deletes
#   backup directories older than seven days. Dumps use pg_dump -Fc for pg_restore.

set -euo pipefail

# PG 容器名（prod 环境）
PG_CONTAINER="myrss-prod-postgres-1"
BACKUP_DIR="./backup/$(date +%Y-%m-%d_%H-%M-%S)"

mkdir -p "$BACKUP_DIR"
BACKUP_PATH="$(cd "$BACKUP_DIR" && pwd)"

echo "💾 开始备份到 $BACKUP_PATH ..."

# Dump each database before emitting stable markers so deploy.sh never accepts a partial backup.
docker exec "$PG_CONTAINER" \
    pg_dump -U postgres -Fc miniflux \
    > "$BACKUP_PATH/miniflux.dump"
echo "  ✅ miniflux.dump"

docker exec "$PG_CONTAINER" \
    pg_dump -U postgres -Fc scoring \
    > "$BACKUP_PATH/scoring.dump"
echo "  ✅ scoring.dump"

# Emit a machine-readable checksum file and stable marker lines for deployment gates.
sha256sum "$BACKUP_PATH/miniflux.dump" "$BACKUP_PATH/scoring.dump" \
    > "$BACKUP_PATH/checksums.txt"
echo "  ✅ checksums.txt"

echo "BACKUP_DIR=$BACKUP_PATH"
echo "BACKUP_SHA256_FILE=$BACKUP_PATH/checksums.txt"
echo "✅ 备份完成：$BACKUP_PATH"
echo "   文件大小："
du -sh "$BACKUP_PATH"/*

# Keep local backup storage bounded without touching freshly written artifacts.
echo "🧹 清理 7 天前的旧备份..."
find ./backup -maxdepth 1 -mindepth 1 -type d -mtime +7 -print -exec rm -rf {} +
echo "✅ 清理完成，当前保留备份："
ls ./backup/
