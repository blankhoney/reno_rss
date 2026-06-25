#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Purpose:
#   Roll back an environment by redeploying a previous image tag through deploy.sh.
#
# Usage:
#   bash infra/scripts/rollback.sh prod v1.2.2
#
# Arguments:
#   $1  ENV  Environment name; must be accepted by deploy.sh.
#   $2  TAG  Previously published image tag to redeploy.
#
# Environment:
#   Inherited by deploy.sh; see infra/scripts/deploy.sh for required .env keys.
#
# Exit codes:
#   0 when deploy.sh succeeds for the requested tag.
#   Non-zero when arguments are missing or deploy.sh fails.
#
# Side effects:
#   Reuses deploy.sh, so it may recreate services, run migrations, and perform
#   prod backup gates depending on the target environment.

set -euo pipefail

ENV="${1:?必须提供环境名，例如 prod 或 staging}"
TAG="${2:?必须提供要回滚到的镜像 tag}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Rollback intentionally shares deploy.sh so recovery and normal deploy gates cannot drift.
echo "⏪ 开始回滚：ENV=$ENV  TARGET_TAG=$TAG"
bash "$SCRIPT_DIR/deploy.sh" "$ENV" "$TAG"
echo "✅ 回滚完成：$ENV 已回到 $TAG"
