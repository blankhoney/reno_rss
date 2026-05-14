#!/usr/bin/env bash
# Runs on the VPS from GitHub Actions. Do not print secrets.

set -euo pipefail

: "${DEPLOY_ENV:?DEPLOY_ENV is required}"
: "${DEPLOY_REF:?DEPLOY_REF is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${IMAGE_REGISTRY:?IMAGE_REGISTRY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${VPS_APP_DIR:?VPS_APP_DIR is required}"

if [[ "$DEPLOY_ENV" != "staging" && "$DEPLOY_ENV" != "prod" ]]; then
    echo "❌ DEPLOY_ENV must be staging or prod, got: $DEPLOY_ENV"
    exit 1
fi

if [[ -n "${GHCR_USERNAME:-}" && -n "${GHCR_TOKEN:-}" ]]; then
    printf '%s' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin >/dev/null
    echo "✅ GHCR login ok"
else
    echo "❌ GHCR_USERNAME/GHCR_TOKEN are required for private image pulls"
    exit 1
fi

cd "$VPS_APP_DIR"

if [[ ! -d .git ]]; then
    echo "❌ VPS_APP_DIR is not a git repository: $VPS_APP_DIR"
    exit 1
fi

dirty="$(git status --porcelain --untracked-files=no)"
if [[ -n "$dirty" ]]; then
    echo "❌ tracked worktree is dirty; clean VPS runtime config before automated deploy"
    echo "$dirty"
    exit 1
fi

git fetch --no-tags origin "$DEPLOY_REF"
git checkout --detach "$DEPLOY_SHA"

export IMAGE_REGISTRY
export LOCAL_BUILD=0
bash infra/scripts/deploy.sh "$DEPLOY_ENV" "$IMAGE_TAG"
bash infra/scripts/smoke-test.sh "$DEPLOY_ENV"
