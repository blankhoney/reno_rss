#!/usr/bin/env bash
# 回滚脚本：用指定旧版本覆盖当前部署
#
# 用法：
#   bash infra/scripts/rollback.sh prod v1.2.2
#
# 本质：回滚 = 用旧 tag 重新 deploy
# 因此直接复用 deploy.sh，保持逻辑一致

set -euo pipefail

ENV="${1:?必须提供环境名，例如 prod 或 staging}"
TAG="${2:?必须提供要回滚到的镜像 tag}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "⏪ 开始回滚：ENV=$ENV  TARGET_TAG=$TAG"
bash "$SCRIPT_DIR/deploy.sh" "$ENV" "$TAG"
echo "✅ 回滚完成：$ENV 已回到 $TAG"
