#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Purpose:
#   Guard deploy.sh against migration-order regressions before they reach VPS deploys.
#
# Usage:
#   bash infra/scripts/check-deploy-migrations.sh [deploy_script] [backup_script]
#
# Arguments:
#   $1  Optional deploy.sh path; defaults to infra/scripts/deploy.sh.
#   $2  Optional backup.sh path; defaults to infra/scripts/backup.sh.
#
# Environment:
#   None.
#
# Exit codes:
#   0 when required markers and ordering invariants are present.
#   Non-zero when a script is missing or a required deploy/backup invariant is absent.
#
# Side effects:
#   Read-only. This script inspects shell source and writes diagnostics to stderr.

set -euo pipefail

SCRIPT_PATH="${1:-infra/scripts/deploy.sh}"
BACKUP_SCRIPT_PATH="${2:-infra/scripts/backup.sh}"

# Validate inputs first so later grep failures always mean invariant failures.
if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "deploy script not found: $SCRIPT_PATH" >&2
    exit 1
fi

if [[ ! -f "$BACKUP_SCRIPT_PATH" ]]; then
    echo "backup script not found: $BACKUP_SCRIPT_PATH" >&2
    exit 1
fi

# These marker checks preserve the fail-closed migration path used by staging and prod.
if ! grep -q 'exec -T ai-reader-api alembic upgrade head' "$SCRIPT_PATH"; then
    echo "deploy.sh must run alembic upgrade head inside ai-reader-api before smoke checks" >&2
    exit 1
fi

if ! grep -q 'PROD_MIGRATION_BACKUP_GATE' "$SCRIPT_PATH"; then
    echo "deploy.sh must gate prod migrations on backup.sh before Alembic upgrade" >&2
    exit 1
fi

if ! grep -q 'API_MIGRATION_READY_GATE' "$SCRIPT_PATH"; then
    echo "deploy.sh must wait for API/DB migration readiness before Alembic upgrade" >&2
    exit 1
fi

# backup.sh must expose stable machine-readable markers instead of localized text.
if ! grep -q 'echo "BACKUP_DIR=' "$BACKUP_SCRIPT_PATH"; then
    echo "backup.sh must emit a stable BACKUP_DIR marker for deploy.sh parsing" >&2
    exit 1
fi

if ! grep -q 'echo "BACKUP_SHA256_FILE=' "$BACKUP_SCRIPT_PATH"; then
    echo "backup.sh must emit a stable BACKUP_SHA256_FILE marker for deploy.sh parsing" >&2
    exit 1
fi

if ! grep -q "s/^BACKUP_DIR=//p" "$SCRIPT_PATH"; then
    echo "deploy.sh must parse BACKUP_DIR marker instead of localized backup output" >&2
    exit 1
fi

if ! grep -q "s/^BACKUP_SHA256_FILE=//p" "$SCRIPT_PATH"; then
    echo "deploy.sh must parse BACKUP_SHA256_FILE marker instead of assuming checksums path" >&2
    exit 1
fi

if grep -q "s/^✅ 备份完成：" "$SCRIPT_PATH"; then
    echo "deploy.sh must not parse localized backup completion text" >&2
    exit 1
fi

# The order check catches accidental deploy refactors that start auth/smoke before schema readiness.
if ! awk '
    /\$\{BACKEND_COMPOSE\[@\]\}" up -d/ { backend_up = NR }
    /PROD_MIGRATION_BACKUP_GATE/ { backup = NR }
    /API_MIGRATION_READY_GATE/ { ready = NR }
    /exec -T ai-reader-api alembic upgrade head/ { migration = NR }
    /up -d --force-recreate --no-deps authelia/ { authelia = NR }
    END {
        ok = backend_up && backup && ready && migration && authelia &&
             backend_up < backup && backup < ready && ready < migration && migration < authelia
        exit !ok
    }
' "$SCRIPT_PATH"; then
    echo "deploy.sh must run backup/readiness gates after backend up and before Alembic/Authelia" >&2
    exit 1
fi
