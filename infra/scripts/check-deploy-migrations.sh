#!/usr/bin/env bash
# Guard deploy.sh against starting API smoke checks before the Alembic schema is applied.

set -euo pipefail

SCRIPT_PATH="${1:-infra/scripts/deploy.sh}"

if [[ ! -f "$SCRIPT_PATH" ]]; then
    echo "deploy script not found: $SCRIPT_PATH" >&2
    exit 1
fi

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
