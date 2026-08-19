#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Run one complete shared-VPS deployment transaction while holding the v1
# cross-project release lock.  The flock FD, rather than metadata TTL, is the
# authority for live ownership.  Metadata is deliberately only an audit and
# crash-recovery aid.

set -euo pipefail

CONTRACT_VERSION=1
# This path is intentionally the same for every service which mutates the
# shared VPS.  SHARED_RELEASE_LOCK_PATH exists only for hermetic tests and for
# a pre-provisioned host-specific mount; production callers must not vary it.
LOCK_PATH="${SHARED_RELEASE_LOCK_PATH:-/var/lib/reno-shared-vps/release.lock}"
METADATA_PATH="${LOCK_PATH}.metadata.json"
AUDIT_DIR="${LOCK_PATH}.audit"

usage() {
    cat >&2 <<'USAGE'
Usage:
  with-shared-release-lock.sh --owner OWNER --repo OWNER/REPO --sha FULL_SHA \
    --run WORKFLOW_RUN --ttl-seconds TTL -- command [args...]

The command is the entire remote mutation transaction: backup, edge recovery,
migrations, activation, probes, rollback, and compensation must all be inside
this wrapper.
USAGE
}

die() {
    printf '%s\n' "shared-release-lock: $*" >&2
    exit 64
}

is_owner() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; }
is_repo() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; }
is_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }
is_positive_integer() { [[ "$1" =~ ^[1-9][0-9]*$ ]]; }

OWNER=''
REPO=''
FULL_SHA=''
WORKFLOW_RUN=''
TTL_SECONDS=''

while (($#)); do
    case "$1" in
        --owner) OWNER="${2:-}"; shift 2 ;;
        --repo) REPO="${2:-}"; shift 2 ;;
        --sha) FULL_SHA="${2:-}"; shift 2 ;;
        --run) WORKFLOW_RUN="${2:-}"; shift 2 ;;
        --ttl-seconds) TTL_SECONDS="${2:-}"; shift 2 ;;
        --) shift; break ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

is_owner "$OWNER" || die "--owner must be a bounded identifier"
is_repo "$REPO" || die "--repo must be OWNER/REPO"
is_sha "$FULL_SHA" || die "--sha must be a 40-character lowercase hexadecimal SHA"
is_positive_integer "$WORKFLOW_RUN" || die "--run must be a positive integer"
is_positive_integer "$TTL_SECONDS" || die "--ttl-seconds must be a positive integer"
(( TTL_SECONDS >= 1 && TTL_SECONDS <= 86400 )) || die "--ttl-seconds must be between 1 and 86400"
(($#)) || die "missing transaction command after --"

command -v flock >/dev/null 2>&1 || die "flock is required; refusing unsafe deployment"
command -v python3 >/dev/null 2>&1 || die "python3 is required to validate lock metadata"
command -v openssl >/dev/null 2>&1 || die "openssl is required to generate the release token"

mkdir -p "$(dirname "$LOCK_PATH")" "$AUDIT_DIR"
chmod 0700 "$AUDIT_DIR"
touch "$LOCK_PATH"
chmod 0600 "$LOCK_PATH"

TOKEN="$(openssl rand -hex 32)"
[[ "$TOKEN" =~ ^[0-9a-f]{64}$ ]] || die "unable to generate a cryptographically strong token"
ACQUIRED_AT=''
EXPIRES_AT=''
LOCK_HELD=0
CHILD_PID=''

utc_now() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }
utc_after_ttl() { date -u -d "+${TTL_SECONDS} seconds" +'%Y-%m-%dT%H:%M:%SZ'; }

# macOS deliberately lacks GNU date -d; production is Linux.  Keeping this
# explicit prevents an unverified local shell from looking like a deployment.
if ! EXPIRES_AT="$(utc_after_ttl 2>/dev/null)"; then
    die "GNU date is required on the remote Linux host"
fi

write_audit() {
    local event="$1"
    local detail="${2:-}"
    local path="$AUDIT_DIR/$(date -u +'%Y%m%dT%H%M%SZ')-${BASHPID}-${RANDOM}-${event}.json"
    umask 077
    python3 - "$path" "$event" "$detail" "$OWNER" "$REPO" "$FULL_SHA" "$WORKFLOW_RUN" "$TOKEN" <<'PY'
import json, sys
from datetime import datetime, timezone

path, event, detail, owner, repo, sha, run, token = sys.argv[1:]
with open(path, "x", encoding="utf-8") as output:
    json.dump({
        "contractVersion": 1,
        "event": event,
        "detail": detail,
        "owner": owner,
        "repo": repo,
        "fullSha": sha,
        "workflowRun": int(run),
        "tokenSha256": __import__("hashlib").sha256(token.encode()).hexdigest(),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }, output, sort_keys=True, separators=(",", ":"))
    output.write("\n")
PY
}

write_metadata() {
    local temporary="${METADATA_PATH}.${BASHPID}.${RANDOM}.tmp"
    umask 077
    python3 - "$temporary" "$OWNER" "$REPO" "$FULL_SHA" "$WORKFLOW_RUN" "$TOKEN" "$ACQUIRED_AT" "$EXPIRES_AT" "$BASHPID" <<'PY'
import json, sys

path, owner, repo, sha, run, token, acquired, expires, pid = sys.argv[1:]
with open(path, "x", encoding="utf-8") as output:
    json.dump({
        "contractVersion": 1,
        "owner": owner,
        "repo": repo,
        "fullSha": sha,
        "workflowRun": int(run),
        "token": token,
        "acquiredAt": acquired,
        "expiresAt": expires,
        "pid": int(pid),
        "audit": {"state": "held", "lastEvent": "acquired"},
    }, output, sort_keys=True, separators=(",", ":"))
    output.write("\n")
PY
    mv -f -- "$temporary" "$METADATA_PATH"
}

quarantine_residual_metadata() {
    [[ -e "$METADATA_PATH" ]] || return 0
    local quarantine="$AUDIT_DIR/quarantine-$(date -u +'%Y%m%dT%H%M%SZ')-${BASHPID}-${RANDOM}.json"
    # We reach this point only after flock succeeded, so no live holder can be
    # using the old metadata.  rename is atomic on this filesystem.
    mv -- "$METADATA_PATH" "$quarantine"
    write_audit "quarantined-residual-metadata" "$quarantine"
}

metadata_matches_current_owner() {
    [[ -f "$METADATA_PATH" ]] || return 1
    python3 - "$METADATA_PATH" "$OWNER" "$REPO" "$FULL_SHA" "$WORKFLOW_RUN" "$TOKEN" <<'PY'
import json, sys

path, owner, repo, sha, run, token = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as source:
        data = json.load(source)
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)

expected_keys = {
    "contractVersion", "owner", "repo", "fullSha", "workflowRun", "token",
    "acquiredAt", "expiresAt", "pid", "audit",
}
if set(data) != expected_keys:
    raise SystemExit(1)
if not isinstance(data["audit"], dict) or set(data["audit"]) != {"state", "lastEvent"}:
    raise SystemExit(1)
if not (
    data["contractVersion"] == 1
    and data["owner"] == owner
    and data["repo"] == repo
    and data["fullSha"] == sha
    and data["workflowRun"] == int(run)
    and data["token"] == token
    and isinstance(data["acquiredAt"], str)
    and isinstance(data["expiresAt"], str)
    and isinstance(data["pid"], int)
    and data["audit"] == {"state": "held", "lastEvent": "acquired"}
):
    raise SystemExit(1)
PY
}

release_lock() {
    (( LOCK_HELD == 1 )) || return 0
    if metadata_matches_current_owner; then
        # This is not a blind deletion: exact owner, repository, SHA, run, and
        # unguessable token were checked immediately before removal.
        rm -- "$METADATA_PATH"
        write_audit "released" "exact-owner-token-match"
    else
        write_audit "release-refused" "metadata-mismatch-or-missing"
    fi
    LOCK_HELD=0
}

on_signal() {
    local signal="$1"
    write_audit "signal" "$signal"
    if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
        kill -TERM "$CHILD_PID" 2>/dev/null || true
        wait "$CHILD_PID" 2>/dev/null || true
    fi
    release_lock
    exit 128
}

on_exit() {
    local status="$?"
    release_lock
    exit "$status"
}

trap 'on_signal TERM' TERM
trap 'on_signal INT' INT
trap on_exit EXIT

exec {LOCK_FD}>"$LOCK_PATH"
if ! flock -n "$LOCK_FD"; then
    printf '%s\n' "shared-release-lock: another release transaction owns $LOCK_PATH" >&2
    exit 75
fi
LOCK_HELD=1

# A TTL is recorded for diagnosis only.  This live flock is never preempted by
# elapsed metadata TTL, so a slow but healthy deployment remains protected.
quarantine_residual_metadata
ACQUIRED_AT="$(utc_now)"
EXPIRES_AT="$(utc_after_ttl)"
write_metadata
write_audit "acquired" "flock-live-owner"

"$@" &
CHILD_PID="$!"
set +e
wait "$CHILD_PID"
TRANSACTION_STATUS="$?"
set -e
CHILD_PID=''
exit "$TRANSACTION_STATUS"
