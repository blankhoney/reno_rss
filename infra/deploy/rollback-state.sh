#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Small, source-only state machine for a failed release transaction.  The
# trusted remote executor owns all deploy mutations; it supplies the three
# callbacks below so rollback semantics cannot be inferred from a failed
# activation alone.

# This file is intentionally not executable as a deployment entrypoint.  It
# must be sourced only by the trusted transaction after it holds the shared
# release lock.

rollback_state_die() {
    echo "rollback state: $*" >&2
    return 1
}

rollback_state_require_sha() {
    local label="$1"
    local value="$2"
    [[ "$value" =~ ^[0-9a-f]{40}$ ]] || rollback_state_die "$label must be a full 40-character lowercase commit SHA"
}

# Print one of:
#   already-rolled-back  current runtime already equals rollbackFrom
#   rollback-required    current runtime still equals the failed target
# Unknown runtime is deliberately an error: it must never be overwritten by a
# compensating activation.
rollback_state_decide() {
    local rollback_from_sha="$1"
    local target_sha="$2"
    local current_runtime_sha="$3"

    rollback_state_require_sha 'rollbackFrom' "$rollback_from_sha" || return
    rollback_state_require_sha 'target' "$target_sha" || return
    rollback_state_require_sha 'current runtime SHA' "$current_runtime_sha" || return
    [[ "$rollback_from_sha" != "$target_sha" ]] || rollback_state_die 'rollbackFrom and target must differ' || return

    case "$current_runtime_sha" in
        "$rollback_from_sha") printf '%s\n' 'already-rolled-back' ;;
        "$target_sha") printf '%s\n' 'rollback-required' ;;
        *) rollback_state_die "refusing compensation: current runtime $current_runtime_sha is neither rollbackFrom nor target" ;;
    esac
}

# Reconcile failed-release compensation with actual runtime state.
#
# Arguments:
#   1 rollbackFrom SHA (the pre-activation known-good runtime)
#   2 target SHA       (the candidate whose activation failed)
#   3 read_runtime     command returning the actual full runtime SHA
#   4 activate         command called as: activate rollbackFrom expectedTarget
#   5 probe            command called as:
#                      probe post-compensation actualRuntime rollbackFrom target
#
# The probe callback receives the actual runtime SHA that must be written into
# the shared-edge receipt.  It is invoked only after the state machine has
# established that runtime.  A post-probe read closes the local race guard: no
# success is returned if the runtime changed before the transaction completed.
rollback_state_compensate() {
    local rollback_from_sha="$1"
    local target_sha="$2"
    local read_runtime="$3"
    local activate="$4"
    local probe="$5"
    local current_runtime_sha decision final_runtime_sha

    [[ -n "$read_runtime" && -n "$activate" && -n "$probe" ]] || rollback_state_die 'read_runtime, activate, and probe callbacks are required' || return

    current_runtime_sha="$($read_runtime)" || {
        rollback_state_die 'cannot read actual current runtime SHA'
        return
    }
    decision="$(rollback_state_decide "$rollback_from_sha" "$target_sha" "$current_runtime_sha")" || return

    case "$decision" in
        already-rolled-back)
            ;;
        rollback-required)
            "$activate" "$rollback_from_sha" "$target_sha" || return
            current_runtime_sha="$($read_runtime)" || {
                rollback_state_die 'cannot read runtime SHA after rollback activation'
                return
            }
            [[ "$current_runtime_sha" == "$rollback_from_sha" ]] || {
                rollback_state_die "rollback activation did not restore rollbackFrom; observed $current_runtime_sha"
                return
            }
            ;;
        *) rollback_state_die "internal error: unknown rollback decision $decision"; return ;;
    esac

    "$probe" post-compensation "$current_runtime_sha" "$rollback_from_sha" "$target_sha" || return

    final_runtime_sha="$($read_runtime)" || {
        rollback_state_die 'cannot read runtime SHA after post-compensation probe'
        return
    }
    [[ "$final_runtime_sha" == "$current_runtime_sha" ]] || {
        rollback_state_die "runtime changed during compensation; expected $current_runtime_sha, observed $final_runtime_sha"
        return
    }

    printf '%s\n' "$decision"
}
