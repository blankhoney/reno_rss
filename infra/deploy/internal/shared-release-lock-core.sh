#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Internal testable implementation; production must invoke the public wrapper.
set -euo pipefail

readonly CONTRACT_VERSION=1
LOCK_ROOT="${SHARED_RELEASE_LOCK_ROOT:-}"
LOCK_PATH=''; METADATA_PATH=''; AUDIT_DIR=''
die() { printf '%s\n' "shared-release-lock: $*" >&2; exit 64; }
is_owner() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; }
is_repo() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; }
is_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }
is_positive_integer() { [[ "$1" =~ ^[1-9][0-9]*$ ]]; }
is_account_name() { [[ "$1" =~ ^[A-Za-z_][A-Za-z0-9_-]{0,127}$ ]]; }

OWNER=''; REPO=''; FULL_SHA=''; WORKFLOW_RUN=''; TTL_SECONDS=''
while (($#)); do
    case "$1" in
        --owner) OWNER="${2:-}"; shift 2 ;;
        --repo) REPO="${2:-}"; shift 2 ;;
        --sha) FULL_SHA="${2:-}"; shift 2 ;;
        --run) WORKFLOW_RUN="${2:-}"; shift 2 ;;
        --ttl-seconds) TTL_SECONDS="${2:-}"; shift 2 ;;
        --) shift; break ;;
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
[[ -n "$LOCK_ROOT" ]] || die "SHARED_RELEASE_LOCK_ROOT is required"
is_account_name "${SHARED_RELEASE_LOCK_OWNER:-}" || die "SHARED_RELEASE_LOCK_OWNER must name the pre-provisioned lock owner"
is_account_name "${SHARED_RELEASE_LOCK_GROUP:-}" || die "SHARED_RELEASE_LOCK_GROUP must name the pre-provisioned lock group"
command -v flock >/dev/null 2>&1 || die "flock is required; refusing unsafe deployment"
command -v python3 >/dev/null 2>&1 || die "python3 is required to validate lock metadata"
command -v openssl >/dev/null 2>&1 || die "openssl is required to generate the release token"
command -v setsid >/dev/null 2>&1 || die "setsid is required to contain the transaction process tree"
[[ "$(uname -s)" == Linux ]] || die "shared release locking is supported only on Linux"

LOCK_PATH="$LOCK_ROOT/release.lock"; METADATA_PATH="$LOCK_ROOT/metadata.json"; AUDIT_DIR="$LOCK_ROOT/audit"
validate_provisioned_path() {
    local path="$1" kind="$2" expected_mode="$3" actual
    [[ ! -L "$path" ]] || die "$kind must not be a symbolic link: $path"
    [[ -e "$path" ]] || die "$kind must be pre-provisioned: $path"
    actual="$(stat -Lc '%F:%U:%G:%a' -- "$path")" || die "cannot stat $kind: $path"
    [[ "$actual" == "$kind:${SHARED_RELEASE_LOCK_OWNER}:${SHARED_RELEASE_LOCK_GROUP}:${expected_mode}" ]] || die "$kind owner, group, or mode does not match the shared-lock contract: $path"
}
validate_lock_filesystem() {
    local type root_device lock_device audit_device
    type="$(stat -fLc '%T' -- "$LOCK_ROOT")" || die "cannot identify lock filesystem"
    # GNU stat reports the ext2/ext3 filesystem magic as the literal
    # `ext2/ext3` on some Linux runners.  Accept only this exact local type.
    case "$type" in 'ext2/ext3'|ext2|ext3|ext4|xfs|btrfs|tmpfs|overlayfs) ;; *) die "lock root must be on a local Linux flock filesystem, got $type" ;; esac
    root_device="$(stat -Lc '%d' -- "$LOCK_ROOT")"; lock_device="$(stat -Lc '%d' -- "$LOCK_PATH")"; audit_device="$(stat -Lc '%d' -- "$AUDIT_DIR")"
    [[ "$root_device" == "$lock_device" && "$root_device" == "$audit_device" ]] || die "root, lock, and audit must share one local filesystem"
}
validate_provisioned_path "$LOCK_ROOT" directory 770
validate_provisioned_path "$LOCK_PATH" 'regular empty file' 660
validate_provisioned_path "$AUDIT_DIR" directory 770
validate_lock_filesystem
[[ -r "$LOCK_PATH" && -w "$LOCK_PATH" && -r "$AUDIT_DIR" && -w "$AUDIT_DIR" && -x "$AUDIT_DIR" ]] || die "current deploy identity lacks the required shared-lock access"

TOKEN="$(openssl rand -hex 32)"; [[ "$TOKEN" =~ ^[0-9a-f]{64}$ ]] || die "unable to generate a cryptographically strong token"
ACQUIRED_AT=''; EXPIRES_AT=''; LOCK_HELD=0; CHILD_PID=''; CHILD_PGID=''; GATE_DIR=''
utc_now() { date -u +'%Y-%m-%dT%H:%M:%SZ'; }
utc_after_ttl() { date -u -d "+${TTL_SECONDS} seconds" +'%Y-%m-%dT%H:%M:%SZ'; }
if ! EXPIRES_AT="$(utc_after_ttl 2>/dev/null)"; then die "GNU date is required on the remote Linux host"; fi

write_audit() {
    local event="$1" detail="${2:-}" path=''
    path="$AUDIT_DIR/$(date -u +'%Y%m%dT%H%M%SZ')-${BASHPID}-${RANDOM}-${event}.json"
    umask 077
    python3 - "$path" "$event" "$detail" "$OWNER" "$REPO" "$FULL_SHA" "$WORKFLOW_RUN" "$TOKEN" "$LOCK_PATH" <<'PY'
import hashlib,json,sys
from datetime import datetime,timezone
path,event,detail,owner,repo,sha,run,token,lock_path=sys.argv[1:]
with open(path,"x",encoding="utf-8") as f:
 json.dump({"contractVersion":1,"event":event,"detail":detail,"owner":owner,"repo":repo,"fullSha":sha,"workflowRun":int(run),"tokenSha256":hashlib.sha256(token.encode()).hexdigest(),"lockPath":lock_path,"timestamp":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},f,sort_keys=True,separators=(",",":"));f.write("\n")
PY
}
write_metadata() {
    local temporary="${METADATA_PATH}.${BASHPID}.${RANDOM}.tmp"
    umask 077
    python3 - "$temporary" "$OWNER" "$REPO" "$FULL_SHA" "$WORKFLOW_RUN" "$TOKEN" "$ACQUIRED_AT" "$EXPIRES_AT" "$BASHPID" "$CHILD_PID" "$CHILD_PGID" "$LOCK_PATH" <<'PY'
import json,sys
path,owner,repo,sha,run,token,acquired,expires,pid,child_pid,child_pgid,lock_path=sys.argv[1:]
with open(path,"x",encoding="utf-8") as f:
 json.dump({"contractVersion":1,"owner":owner,"repo":repo,"fullSha":sha,"workflowRun":int(run),"token":token,"acquiredAt":acquired,"expiresAt":expires,"pid":int(pid),"childPid":int(child_pid),"childPgid":int(child_pgid),"lock":{"authority":"live-flock","ttl":"diagnostic-only","path":lock_path},"audit":{"state":"held","lastEvent":"acquired"}},f,sort_keys=True,separators=(",",":"));f.write("\n")
PY
    mv -f -- "$temporary" "$METADATA_PATH"
}
quarantine_residual_metadata() {
    [[ -e "$METADATA_PATH" || -L "$METADATA_PATH" ]] || return 0
    local quarantine="$AUDIT_DIR/quarantine-$(date -u +'%Y%m%dT%H%M%SZ')-${BASHPID}-${RANDOM}.json"
    mv -- "$METADATA_PATH" "$quarantine"; write_audit "quarantined-residual-metadata" "$quarantine"
}
quarantine_residual_gates() {
    local gate=''
    shopt -s nullglob
    for gate in "$LOCK_ROOT"/.transaction-gate.*; do
        [[ -d "$gate" && ! -L "$gate" ]] || die "residual transaction gate is not a safe directory: $gate"
        [[ ! -e "$gate/start" || ( -f "$gate/start" && ! -L "$gate/start" ) ]] || die "residual transaction gate is unsafe: $gate/start"
        write_audit 'quarantined-residual-transaction-gate' "$gate"
        [[ ! -e "$gate/start" ]] || rm -- "$gate/start"
        rmdir -- "$gate"
    done
    shopt -u nullglob
}
cleanup_transaction_gate() {
    [[ -n "$GATE_DIR" ]] || return 0
    if [[ -d "$GATE_DIR" && ! -L "$GATE_DIR" ]]; then
        [[ ! -e "$GATE_DIR/start" ]] || rm -- "$GATE_DIR/start"
        rmdir -- "$GATE_DIR"
    fi
    GATE_DIR=''
}
metadata_matches_current_owner() {
    [[ -f "$METADATA_PATH" && ! -L "$METADATA_PATH" ]] || return 1
    python3 - "$METADATA_PATH" "$OWNER" "$REPO" "$FULL_SHA" "$WORKFLOW_RUN" "$TOKEN" "$LOCK_PATH" <<'PY'
import json,sys
path,owner,repo,sha,run,token,lock_path=sys.argv[1:]
try:
 with open(path,encoding="utf-8") as f:data=json.load(f)
except (OSError,json.JSONDecodeError):raise SystemExit(1)
if set(data)!={"contractVersion","owner","repo","fullSha","workflowRun","token","acquiredAt","expiresAt","pid","childPid","childPgid","lock","audit"}:raise SystemExit(1)
if data.get("audit")!={"state":"held","lastEvent":"acquired"}:raise SystemExit(1)
if data.get("lock")!={"authority":"live-flock","ttl":"diagnostic-only","path":lock_path}:raise SystemExit(1)
if not (data["contractVersion"]==1 and data["owner"]==owner and data["repo"]==repo and data["fullSha"]==sha and data["workflowRun"]==int(run) and data["token"]==token and isinstance(data["acquiredAt"],str) and isinstance(data["expiresAt"],str) and isinstance(data["pid"],int) and isinstance(data["childPid"],int) and isinstance(data["childPgid"],int) and data["childPid"]==data["childPgid"]):raise SystemExit(1)
PY
}
release_lock() {
    (( LOCK_HELD == 1 )) || return 0
    cleanup_transaction_gate
    if metadata_matches_current_owner; then rm -- "$METADATA_PATH"; write_audit released exact-owner-token-match; else write_audit release-refused metadata-mismatch-or-missing; fi
    LOCK_HELD=0
}
transaction_group_alive() {
    [[ -n "$CHILD_PGID" ]] || return 1
    python3 - "$CHILD_PGID" <<'PY'
import glob
import sys

target = int(sys.argv[1])
for path in glob.glob("/proc/[0-9]*/stat"):
    try:
        raw = open(path, encoding="utf-8").read()
        fields = raw.rsplit(")", 1)[1].split()
        state, process_group = fields[0], int(fields[2])
    except (OSError, ValueError, IndexError):
        continue
    if process_group == target and state != "Z":
        raise SystemExit(0)
raise SystemExit(1)
PY
}
wait_for_transaction_group() {
    local cancelling="${1:-0}" status=0 elapsed=0 child_state=''
    if (( cancelling == 0 )) && [[ -n "$CHILD_PID" ]]; then
        wait "$CHILD_PID" || status="$?"
    fi
    while transaction_group_alive; do
        # Reap a dead session leader so its zombie cannot make kill(-PGID, 0)
        # look like a live mutation tree forever.  Descendants retain the PGID
        # and are still checked independently after the leader is reaped.
        if [[ -n "$CHILD_PID" && -r "/proc/$CHILD_PID/stat" ]]; then
            child_state="$(awk '{print $3}' "/proc/$CHILD_PID/stat")"
            if [[ "$child_state" == Z ]]; then
                wait "$CHILD_PID" || status="$?"
                CHILD_PID=''
            fi
        fi
        elapsed=$((elapsed + 1))
        if (( cancelling == 1 && elapsed == 20 )); then
            write_audit 'signal-escalated' 'TERM-to-KILL-after-2-seconds'
            kill -KILL -- "-$CHILD_PGID" 2>/dev/null || true
        fi
        if (( cancelling == 1 && elapsed == 40 )); then
            # A PID/PGID we cannot prove dead must retain the kernel flock.
            write_audit 'release-refused' 'transaction-process-group-still-live'
        fi
        sleep 0.1
    done
    if (( cancelling == 1 )) && [[ -n "$CHILD_PID" ]]; then
        wait "$CHILD_PID" || status="$?"
    fi
    CHILD_PID=''; CHILD_PGID=''
    return "$status"
}
on_signal() {
    local signal="$1" signal_status=128
    case "$signal" in TERM) signal_status=143 ;; INT) signal_status=130 ;; HUP) signal_status=129 ;; esac
    write_audit signal "$signal"
    if transaction_group_alive; then kill -"$signal" -- "-$CHILD_PGID" 2>/dev/null || true; fi
    set +e; wait_for_transaction_group 1; set -e
    write_audit cancelled "$signal"
    release_lock; exit "$signal_status"
}
on_exit() { local status="$?"; release_lock; exit "$status"; }
trap 'on_signal TERM' TERM; trap 'on_signal INT' INT; trap 'on_signal HUP' HUP; trap on_exit EXIT
if [[ -n "${SHARED_RELEASE_LOCK_CORE_FD:-}" ]]; then
    [[ "$SHARED_RELEASE_LOCK_CORE_FD" =~ ^[0-9]+$ && -e "/proc/self/fd/$SHARED_RELEASE_LOCK_CORE_FD" ]] || die "invalid inherited core lock FD"
    LOCK_FD="$SHARED_RELEASE_LOCK_CORE_FD"
    [[ "$(readlink -f -- "/proc/self/fd/$LOCK_FD")" == "$(readlink -f -- "$LOCK_PATH")" ]] || die "inherited core lock FD does not reference the configured release.lock"
else
    exec {LOCK_FD}>"$LOCK_PATH"
fi
if ! flock -n "$LOCK_FD"; then printf '%s\n' "shared-release-lock: another release transaction owns $LOCK_PATH" >&2; exit 75; fi
LOCK_HELD=1
# A metadata TTL is diagnostic only; the live kernel flock is authoritative.
quarantine_residual_metadata; quarantine_residual_gates; ACQUIRED_AT="$(utc_now)"; EXPIRES_AT="$(utc_after_ttl)"
# A dedicated session makes the transaction's PID its process-group ID. The
# open flock descriptor is deliberately inherited by this tree as crash cover.
GATE_DIR="$LOCK_ROOT/.transaction-gate.${BASHPID}.${RANDOM}"
(umask 077; mkdir -- "$GATE_DIR")
setsid -- bash -c '
parent_pid="$1"; start_file="$2"; shift 2
while [[ ! -f "$start_file" ]]; do
    kill -0 "$parent_pid" 2>/dev/null || exit 125
    sleep 0.01
done
exec "$@"
' bash "$BASHPID" "$GATE_DIR/start" "$@" & CHILD_PID="$!"; CHILD_PGID="$CHILD_PID"
write_metadata; write_audit acquired flock-live-owner
(umask 077; : > "$GATE_DIR/start")
set +e; wait_for_transaction_group 0; TRANSACTION_STATUS="$?"; set -e
exit "$TRANSACTION_STATUS"
