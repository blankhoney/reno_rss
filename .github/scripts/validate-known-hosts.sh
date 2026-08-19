#!/usr/bin/env bash
# Validate that the trusted known_hosts bundle contains the exact VPS host token
# for the SSH port that the deployment will use. Never learn trust from network.

set -euo pipefail

die() {
    printf '%s\n' "known-hosts contract: $*" >&2
    exit 1
}

(( $# == 0 )) || die 'this validator accepts no arguments'
: "${VPS_HOST:?VPS_HOST is required}"
: "${VPS_PORT:?VPS_PORT is required}"
: "${VPS_KNOWN_HOSTS_FILE:?VPS_KNOWN_HOSTS_FILE is required}"

[[ "$VPS_HOST" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}[A-Za-z0-9]$ ]] \
    || die 'VPS_HOST must be a bounded hostname or IPv4 address without SSH options'
[[ "$VPS_HOST" != *..* ]] || die 'VPS_HOST contains an empty label'
[[ "$VPS_PORT" =~ ^[1-9][0-9]{0,4}$ ]] || die 'VPS_PORT must be a positive integer'
(( VPS_PORT <= 65535 )) || die 'VPS_PORT must not exceed 65535'

[[ "$VPS_KNOWN_HOSTS_FILE" == /* ]] || die 'known_hosts path must be absolute'
[[ ! -L "$VPS_KNOWN_HOSTS_FILE" ]] || die 'known_hosts path must not be a symlink'
[[ -f "$VPS_KNOWN_HOSTS_FILE" && -s "$VPS_KNOWN_HOSTS_FILE" ]] \
    || die 'known_hosts must be a non-empty regular file'

mode="$(stat -f '%Lp' "$VPS_KNOWN_HOSTS_FILE" 2>/dev/null || stat -c '%a' "$VPS_KNOWN_HOSTS_FILE")"
[[ "$mode" == '600' ]] || die 'known_hosts must have mode 0600'
command -v ssh-keygen >/dev/null 2>&1 || die 'ssh-keygen is required'

lookup="$VPS_HOST"
if [[ "$VPS_PORT" != '22' ]]; then
    lookup="[$VPS_HOST]:$VPS_PORT"
fi

ssh-keygen -F "$lookup" -f "$VPS_KNOWN_HOSTS_FILE" >/dev/null \
    || die 'trusted known_hosts has no entry for the exact VPS host and port'

echo 'known-hosts contract passed for the configured VPS endpoint'
