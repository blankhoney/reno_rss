#!/usr/bin/env bash
set -euo pipefail

missing=()
required=(
  "SSH_KEY:VPS_SSH_KEY"
  "VPS_HOST:VPS_HOST"
  "VPS_USER:VPS_USER"
  "VPS_APP_DIR:VPS_APP_DIR"
  "GHCR_USERNAME:GHCR_USERNAME"
  "GHCR_TOKEN:GHCR_TOKEN"
)

for item in "${required[@]}"; do
  var_name="${item%%:*}"
  secret_name="${item#*:}"
  if [[ -z "${!var_name:-}" ]]; then
    missing+=("$secret_name")
  fi
done

if (( ${#missing[@]} > 0 )); then
  printf '::error title=Missing deploy secrets::Configure repository or environment secrets: %s\n' "${missing[*]}"
  exit 1
fi
