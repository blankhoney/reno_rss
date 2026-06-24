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

if ! awk '
    /\$\{BACKEND_COMPOSE\[@\]\}" up -d/ { backend_up = NR }
    /exec -T ai-reader-api alembic upgrade head/ { migration = NR }
    /up -d --force-recreate --no-deps authelia/ { authelia = NR }
    END {
        exit !(backend_up && migration && authelia && backend_up < migration && migration < authelia)
    }
' "$SCRIPT_PATH"; then
    echo "deploy.sh must run Alembic after backend up and before Authelia reload" >&2
    exit 1
fi
