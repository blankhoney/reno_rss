#!/usr/bin/env bash
set -euo pipefail

key_file="${1:?key file path is required}"

if [[ -n "${SSH_KEY_B64:-}" ]]; then
  printf '%s' "$SSH_KEY_B64" | base64 --decode > "$key_file"
elif [[ -n "${SSH_KEY:-}" ]]; then
  printf '%s\n' "$SSH_KEY" > "$key_file"
else
  printf '::error title=Missing SSH key::Configure VPS_SSH_KEY_B64 or VPS_SSH_KEY\n'
  exit 1
fi

chmod 600 "$key_file"
