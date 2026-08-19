#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Public production entrypoint for the shared VPS release-lock v1 contract.
set -euo pipefail

readonly CANONICAL_LOCK_ROOT='/var/lib/reno-shared-vps/release-lock-v1'
die() { printf '%s\n' "shared-release-lock: $*" >&2; exit 64; }

# The public API has no path fallback, test mode, or alternate-root interface.
# Even the canonical path is rejected when supplied by a caller: the wrapper is
# the sole source of truth and passes the root to the private core itself.
for forbidden in SHARED_RELEASE_LOCK_ROOT SHARED_RELEASE_LOCK_PATH SHARED_RELEASE_LOCK_TEST_MODE SHARED_RELEASE_LOCK_INHERITED_FD SHARED_RELEASE_LOCK_CORE_FD SHARED_RELEASE_LOCK_TOKEN SHARED_RELEASE_LOCK_METADATA_PATH SHARED_RELEASE_LOCK_AUDIT_DIR; do
    [[ -z "${!forbidden:-}" ]] || die "$forbidden is forbidden by the production wrapper"
done
if env | command grep -q '^SHARED_RELEASE_LOCK_INTERNAL_'; then
    die 'internal shared-lock overrides are forbidden by the production wrapper'
fi
[[ "$(uname -s)" == Linux ]] || die 'shared release locking is supported only on Linux'
[[ -n "${SHARED_RELEASE_LOCK_OWNER:-}" && -n "${SHARED_RELEASE_LOCK_GROUP:-}" ]] || die 'shared-lock owner and group are required'

lock_path="$CANONICAL_LOCK_ROOT/release.lock"
audit_dir="$CANONICAL_LOCK_ROOT/audit"
validate_path() {
    local path="$1" kind="$2" mode="$3" actual
    [[ ! -L "$path" && -e "$path" ]] || die "pre-provisioned $kind is missing or symbolic-linked: $path"
    actual="$(stat -Lc '%F:%U:%G:%a' -- "$path")" || die "cannot stat pre-provisioned $kind"
    [[ "$actual" == "$kind:${SHARED_RELEASE_LOCK_OWNER}:${SHARED_RELEASE_LOCK_GROUP}:$mode" ]] || die "pre-provisioned $kind violates owner, group, or mode contract"
}
validate_path "$CANONICAL_LOCK_ROOT" directory 770
validate_path "$lock_path" 'regular empty file' 660
validate_path "$audit_dir" directory 770
filesystem_type="$(stat -fLc '%T' -- "$CANONICAL_LOCK_ROOT")"
case "$filesystem_type" in ext2|ext3|ext4|xfs|btrfs|tmpfs|overlayfs) ;; *) die "lock root must be on a local Linux flock filesystem" ;; esac
[[ "$(stat -Lc '%d' -- "$CANONICAL_LOCK_ROOT")" == "$(stat -Lc '%d' -- "$lock_path")" && "$(stat -Lc '%d' -- "$CANONICAL_LOCK_ROOT")" == "$(stat -Lc '%d' -- "$audit_dir")" ]] || die 'shared-lock paths must share one filesystem'
[[ -r "$lock_path" && -w "$lock_path" && -r "$audit_dir" && -w "$audit_dir" && -x "$audit_dir" ]] || die 'current deploy identity lacks shared-lock access'

# The public entrypoint owns the canonical FD before it enters core.  Core is
# told only this descriptor after hostile caller-provided overrides were rejected.
exec {PUBLIC_LOCK_FD}>"$lock_path"
if ! flock -n "$PUBLIC_LOCK_FD"; then
    printf '%s\n' "shared-release-lock: another release transaction owns $lock_path" >&2
    exit 75
fi
export SHARED_RELEASE_LOCK_CORE_FD="$PUBLIC_LOCK_FD"
export SHARED_RELEASE_LOCK_ROOT="$CANONICAL_LOCK_ROOT"
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/internal/shared-release-lock-core.sh" "$@"
