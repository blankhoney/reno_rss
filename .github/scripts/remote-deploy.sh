#!/usr/bin/env bash
# Runs on the VPS from GitHub Actions. Do not print secrets.

set -euo pipefail

docker_config_dir=""

cleanup_docker_config() {
    local exit_code=$?
    trap - EXIT HUP INT TERM
    if [[ -n "$docker_config_dir" ]]; then
        rm -rf -- "$docker_config_dir" || true
    fi
    exit "$exit_code"
}

trap cleanup_docker_config EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

docker_config_dir="$(mktemp -d)"
chmod 700 "$docker_config_dir"
export DOCKER_CONFIG="$docker_config_dir"

: "${DEPLOY_ENV:?DEPLOY_ENV is required}"
: "${DEPLOY_REF:?DEPLOY_REF is required}"
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${IMAGE_REGISTRY:?IMAGE_REGISTRY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${VPS_APP_DIR:?VPS_APP_DIR is required}"
: "${GHCR_TOKEN_B64:?GHCR_TOKEN_B64 is required}"

if [[ "$DEPLOY_ENV" != "staging" && "$DEPLOY_ENV" != "prod" ]]; then
    echo "❌ DEPLOY_ENV must be staging or prod, got: $DEPLOY_ENV"
    exit 1
fi

case "$DEPLOY_REF" in
    main) ;;
    refs/tags/release-?*)
        git check-ref-format "$DEPLOY_REF" >/dev/null 2>&1 || {
            echo "❌ DEPLOY_REF must be a valid release tag ref"
            exit 1
        }
        ;;
    *)
        echo "❌ DEPLOY_REF must be main or refs/tags/release-*"
        exit 1
        ;;
esac

if [[ ! "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]; then
    echo "❌ DEPLOY_SHA must be a full commit SHA"
    exit 1
fi

if [[ -n "${GHCR_USERNAME:-}" ]]; then
    printf '%s' "$GHCR_TOKEN_B64" | base64 --decode | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin >/dev/null
    unset GHCR_TOKEN_B64
    echo "✅ GHCR login ok"
else
    echo "❌ GHCR_USERNAME/GHCR_TOKEN_B64 are required for private image pulls"
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
fetched_sha="$(git rev-parse 'FETCH_HEAD^{commit}')"
if [[ "$fetched_sha" != "$DEPLOY_SHA" ]]; then
    echo "❌ fetched commit does not match DEPLOY_SHA"
    exit 1
fi
git checkout --detach "$DEPLOY_SHA"

export IMAGE_REGISTRY
export LOCAL_BUILD=0

run_gate() {
    local name="$1"
    shift
    echo "▶ $name"
    "$@" </dev/null
    echo "✅ $name passed"
}

run_gate "deploy $DEPLOY_ENV" bash infra/scripts/deploy.sh "$DEPLOY_ENV" "$IMAGE_TAG"
run_gate "smoke test $DEPLOY_ENV" bash infra/scripts/smoke-test.sh "$DEPLOY_ENV"

if [[ "$DEPLOY_ENV" == "staging" && "${RUN_STAGING_RUNTIME_PROOF:-0}" == "1" ]]; then
    run_gate "staging runtime proof" bash infra/scripts/staging-runtime-proof.sh "$DEPLOY_ENV"
fi
