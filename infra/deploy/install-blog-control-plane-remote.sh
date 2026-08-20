#!/usr/bin/env bash
# One-time RSS-owned installer transport. The remote side performs only
# read-only preflight before the canonical public wrapper owns the flock.
set -euo pipefail

readonly HELPER_ROOT='/usr/local/lib/reno-shared-vps/release-lock-v1'
readonly WRAPPER="$HELPER_ROOT/with-shared-release-lock.sh"
readonly CORE="$HELPER_ROOT/internal/shared-release-lock-core.sh"
readonly WRAPPER_SHA256='2cf87eb5d54e626fd96bef70ea7b8543ef721a12bb610b31dd2578fb80c296a5'
readonly CORE_SHA256='d54485e473c7729e74628105c0f0ca6f75bcc63e65d4b71c2f14f1e2f3b51429'

[[ "$#" -eq 16 ]] || { echo 'usage: install-blog-control-plane-remote.sh BUNDLE CONTROL_SHA OPERATION_SHA REPO INSTALL_RUN INSTALL_ATTEMPT RSS_SOURCE_SHA RSS_INSTALLER_SHA CONTROL_CI_RUN CONTROL_CI_ATTEMPT PRODUCER_RUN PRODUCER_ATTEMPT ARTIFACT_ID ARTIFACT_DIGEST WEB_DIGEST COMPANION_DIGEST' >&2; exit 64; }
BUNDLE=$1; CONTROL_SHA=$2; OPERATION_SHA=$3; REPO=$4; INSTALL_RUN=$5
INSTALL_ATTEMPT=$6; RSS_SOURCE_SHA=$7; RSS_INSTALLER_SHA=$8; CONTROL_CI_RUN=$9
CONTROL_CI_ATTEMPT=${10}; PRODUCER_RUN=${11}; PRODUCER_ATTEMPT=${12}
ARTIFACT_ID=${13}; ARTIFACT_DIGEST=${14}; WEB_DIGEST=${15}; COMPANION_DIGEST=${16}

: "${DEPLOY_HOST:?}" "${DEPLOY_USER:?}" "${DEPLOY_PORT:?}" \
  "${DEPLOY_SSH_KEY_PATH:?}" "${DEPLOY_KNOWN_HOSTS_PATH:?}"
[[ -f "$BUNDLE" && ! -L "$BUNDLE" ]] || { echo 'unsafe installer bundle' >&2; exit 65; }
[[ "$DEPLOY_PORT" =~ ^[1-9][0-9]{0,4}$ ]] && (( DEPLOY_PORT <= 65535 )) || exit 64
for sha in "$CONTROL_SHA" "$OPERATION_SHA" "$RSS_SOURCE_SHA" "$RSS_INSTALLER_SHA"; do
  [[ "$sha" =~ ^[a-f0-9]{40}$ ]] || exit 64
done
[[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || exit 64
for value in "$INSTALL_RUN" "$INSTALL_ATTEMPT" "$CONTROL_CI_RUN" "$CONTROL_CI_ATTEMPT" "$PRODUCER_RUN" "$PRODUCER_ATTEMPT" "$ARTIFACT_ID"; do
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || exit 64
done
for digest in "$ARTIFACT_DIGEST" "$WEB_DIGEST" "$COMPANION_DIGEST"; do
  [[ "$digest" =~ ^sha256:[a-f0-9]{64}$ ]] || exit 64
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
INNER="$SCRIPT_DIR/install-blog-control-plane-transaction.py"
[[ -f "$INNER" && ! -L "$INNER" ]] || exit 65
inner_before="$(sha256sum "$INNER" | cut -d ' ' -f 1)"
inner_source="$(<"$INNER")"
[[ "$(sha256sum "$INNER" | cut -d ' ' -f 1)" == "$inner_before" ]] || exit 65
inner_exec_digest="$(printf '%s' "$inner_source" | sha256sum | cut -d ' ' -f 1)"

quote() { printf '%q' "$1"; }
inner_command="exec python3 -c $(quote "$inner_source") --bundle-fd 8 --repo $(quote "$REPO") \
--installer-transaction-sha256 $(quote "$inner_exec_digest") \
--control-plane-sha $(quote "$CONTROL_SHA") --operation-sha $(quote "$OPERATION_SHA") \
--installer-run $(quote "$INSTALL_RUN") --installer-attempt $(quote "$INSTALL_ATTEMPT") \
--rss-source-sha $(quote "$RSS_SOURCE_SHA") --rss-installer-sha $(quote "$RSS_INSTALLER_SHA") \
--control-ci-run $(quote "$CONTROL_CI_RUN") --control-ci-attempt $(quote "$CONTROL_CI_ATTEMPT") \
--producer-run $(quote "$PRODUCER_RUN") --producer-attempt $(quote "$PRODUCER_ATTEMPT") \
--artifact-id $(quote "$ARTIFACT_ID") --artifact-digest $(quote "$ARTIFACT_DIGEST") \
--web-image-digest $(quote "$WEB_DIGEST") --companion-image-digest $(quote "$COMPANION_DIGEST") \
--probe-uid \$INSTALLER_PROBE_UID --probe-gid \$INSTALLER_PROBE_GID"
sudo_command="exec 8<&0; exec env RENO_SHARED_RELEASE_BUNDLE_FD=8 $(quote "$WRAPPER") \
--owner blog --repo $(quote "$REPO") --sha $(quote "$OPERATION_SHA") --run $(quote "$INSTALL_RUN") \
--ttl-seconds 900 -- bash -c $(quote "$inner_command")"
remote="set -euo pipefail
root=$(quote "$HELPER_ROOT"); wrapper=$(quote "$WRAPPER"); core=$(quote "$CORE")
for path in \"\$root\" \"\$wrapper\" \"\$core\"; do
  [[ -e \"\$path\" && ! -L \"\$path\" ]] || exit 65
done
[[ -d \"\$root\" && -f \"\$wrapper\" && -f \"\$core\" ]] || exit 65
[[ \"\$(sha256sum \"\$wrapper\" | cut -d ' ' -f 1)\" == $(quote "$WRAPPER_SHA256") ]] || exit 65
[[ \"\$(sha256sum \"\$core\" | cut -d ' ' -f 1)\" == $(quote "$CORE_SHA256") ]] || exit 65
command -v sudo >/dev/null
probe_uid=\"\$(id -u)\"; probe_gid=\"\$(id -g)\"
[[ \"\$probe_uid\" =~ ^[1-9][0-9]*$ && \"\$probe_gid\" =~ ^[0-9]+$ ]] || exit 69
exec sudo -n env INSTALLER_PROBE_UID=\"\$probe_uid\" \
  INSTALLER_PROBE_GID=\"\$probe_gid\" bash -c $(quote "$sudo_command")"

exec ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile="$DEPLOY_KNOWN_HOSTS_PATH" -i "$DEPLOY_SSH_KEY_PATH" \
  -p "$DEPLOY_PORT" "$DEPLOY_USER@$DEPLOY_HOST" "$remote" < "$BUNDLE"
