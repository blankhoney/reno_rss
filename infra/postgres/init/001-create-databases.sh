#!/usr/bin/env bash
# 只在 PostgreSQL 数据目录为空时执行一次（容器首次启动）
# 创建 miniflux 和 scoring 两个独立用户+数据库
# 变量由 docker-compose.base.yml 中的 environment 传入
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    -- miniflux 业务库：供 Miniflux 应用使用
    CREATE USER miniflux WITH PASSWORD '${POSTGRES_MINIFLUX_PASSWORD}';
    CREATE DATABASE miniflux OWNER miniflux;

    -- scoring 评分库：供 Scoring Worker 使用（独立隔离，互不影响）
    CREATE USER scoring WITH PASSWORD '${POSTGRES_SCORING_PASSWORD}';
    CREATE DATABASE scoring OWNER scoring;
EOSQL

echo "✅ Databases miniflux and scoring created successfully."
