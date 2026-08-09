#!/usr/bin/env bash
# Runs on the VPS from GitHub Actions. Do not print secrets.

set -euo pipefail

docker_config_dir=""

cleanup_docker_config() {
    local exit_code=$?
    trap - EXIT HUP INT TERM
    unset GHCR_TOKEN_B64 ghcr_token_b64
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
: "${DEPLOY_SHA:?DEPLOY_SHA is required}"
: "${IMAGE_REGISTRY:?IMAGE_REGISTRY is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
: "${VPS_APP_DIR:?VPS_APP_DIR is required}"
: "${GHCR_USERNAME:?GHCR_USERNAME is required}"
: "${GHCR_TOKEN_B64:?GHCR_TOKEN_B64 is required}"

ghcr_token_b64="$GHCR_TOKEN_B64"
unset GHCR_TOKEN_B64
export -n ghcr_token_b64

# Automated deploys always resolve the trusted main branch. Do not let a caller,
# request artifact, or rollback input select a different ref at this boundary.
readonly DEPLOY_REF="refs/heads/main"
readonly DEPLOY_REMOTE_REF="refs/remotes/origin/main"

if [[ "$DEPLOY_ENV" != "staging" && "$DEPLOY_ENV" != "prod" ]]; then
    echo "❌ DEPLOY_ENV must be staging or prod, got: $DEPLOY_ENV"
    exit 1
fi

if [[ ! "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]]; then
    echo "❌ DEPLOY_SHA must be a full 40-character lowercase commit SHA"
    exit 1
fi

if [[ ! "$IMAGE_TAG" =~ ^sha-[0-9a-f]{7}$ ]]; then
    echo "❌ IMAGE_TAG must match the immutable sha-<7 lowercase hex> format"
    exit 1
fi
expected_image_tag="sha-${DEPLOY_SHA:0:7}"
if [[ "$IMAGE_TAG" != "$expected_image_tag" ]]; then
    echo "❌ IMAGE_TAG must match the first seven characters of DEPLOY_SHA"
    exit 1
fi

# Local replace refs must never rewrite the commit graph used for ancestry or checkout.
export GIT_NO_REPLACE_OBJECTS=1

reject_legacy_grafts() {
    local grafts_path
    grafts_path="$(git --no-replace-objects rev-parse --git-path info/grafts 2>/dev/null)" || {
        echo "❌ unable to resolve the legacy graft file path"
        exit 1
    }
    if [[ -z "$grafts_path" ]]; then
        echo "❌ legacy graft file path is empty"
        exit 1
    fi
    if [[ -s "$grafts_path" ]]; then
        echo "❌ legacy Git grafts are not allowed for automated deploy"
        exit 1
    fi
}

cd "$VPS_APP_DIR"

if [[ ! -d .git ]]; then
    echo "❌ VPS_APP_DIR is not a git repository: $VPS_APP_DIR"
    exit 1
fi

dirty="$(git --no-replace-objects status --porcelain --untracked-files=all)"
if [[ -n "$dirty" ]]; then
    echo "❌ VPS worktree is dirty; clean VPS runtime config before automated deploy"
    echo "$dirty"
    exit 1
fi

reject_legacy_grafts

shallow_repository="$(git --no-replace-objects rev-parse --is-shallow-repository 2>/dev/null)" || {
    echo "❌ unable to determine whether the VPS repository is shallow"
    exit 1
}
if [[ "$shallow_repository" != "false" ]]; then
    echo "❌ refusing automated deploy from a shallow VPS repository"
    exit 1
fi

# Keep the fetched branch in a deterministic remote-tracking ref. The implicit
# fetch result is not a trust anchor because it can contain other refs.
git --no-replace-objects fetch --no-tags origin "$DEPLOY_REF:$DEPLOY_REMOTE_REF"
# A remote helper can mutate local metadata while fetch runs; re-check before
# reading any object or history so a newly-created graft cannot bypass ancestry.
reject_legacy_grafts
main_tip="$(git --no-replace-objects rev-parse --verify "$DEPLOY_REMOTE_REF^{commit}")" || {
    echo "❌ unable to resolve the fetched main tip"
    exit 1
}
if [[ ! "$main_tip" =~ ^[0-9a-f]{40}$ ]]; then
    echo "❌ fetched main tip is not a full lowercase commit SHA"
    exit 1
fi

if ! git --no-replace-objects cat-file -e "$DEPLOY_SHA^{commit}" 2>/dev/null; then
    echo "❌ DEPLOY_SHA commit object is missing from the VPS repository"
    exit 1
fi

ancestor_status=0
git --no-replace-objects merge-base --is-ancestor "$DEPLOY_SHA" "$main_tip" || ancestor_status=$?
if (( ancestor_status == 1 )); then
    echo "❌ DEPLOY_SHA is not an ancestor of the fetched main tip"
    exit 1
elif (( ancestor_status != 0 )); then
    echo "❌ unable to verify DEPLOY_SHA ancestry against the fetched main tip"
    exit 1
fi

git --no-replace-objects checkout --detach "$DEPLOY_SHA"

docker_login_status=0
printf '%s' "$ghcr_token_b64" | base64 --decode | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin >/dev/null || docker_login_status=$?
unset ghcr_token_b64
if (( docker_login_status != 0 )); then
    exit "$docker_login_status"
fi
echo "✅ GHCR login ok"

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
