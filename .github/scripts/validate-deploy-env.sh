#!/usr/bin/env bash
set -euo pipefail

missing=()
required=(
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

if [[ -z "${SSH_KEY:-}" && -z "${SSH_KEY_B64:-}" ]]; then
  missing+=("VPS_SSH_KEY or VPS_SSH_KEY_B64")
fi

if (( ${#missing[@]} > 0 )); then
  printf '::error title=Missing deploy secrets::Configure repository or environment secrets: %s\n' "${missing[*]}"
  exit 1
fi
