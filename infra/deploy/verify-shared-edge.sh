#!/usr/bin/env bash
set -euo pipefail

CONTRACT_VERSION=1
CADDY_CONTAINER='myrss-edge-caddy-1'
BLOG_URL='https://blog.blankhoney.xyz/zh'
BLOG_STATUS_URL='https://blog.blankhoney.xyz/api/status'
RSS_URL='https://ai-reader.blankhoney.xyz/'
OWNER_PROJECT=''
OWNER_REPO=''
OPERATION_SHA=''
RUNTIME_SHA=''
WORKFLOW_RUN=''
PHASE=''
RECEIPT=''
ROLLBACK_FROM_SHA=''
ROLLBACK_TARGET_SHA=''

usage() {
  echo 'usage: verify-shared-edge.sh --owner-project NAME --owner-repo OWNER/REPO --operation-sha FULL_SHA --runtime-sha FULL_SHA --workflow-run RUN --phase PHASE --receipt ABSOLUTE_PATH [--rollback-from-sha FULL_SHA --rollback-target-sha FULL_SHA]' >&2
  exit 64
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --owner-project) [[ "$#" -ge 2 ]] || usage; OWNER_PROJECT="$2"; shift 2 ;;
    --owner-repo) [[ "$#" -ge 2 ]] || usage; OWNER_REPO="$2"; shift 2 ;;
    --operation-sha) [[ "$#" -ge 2 ]] || usage; OPERATION_SHA="$2"; shift 2 ;;
    --runtime-sha) [[ "$#" -ge 2 ]] || usage; RUNTIME_SHA="$2"; shift 2 ;;
    --workflow-run) [[ "$#" -ge 2 ]] || usage; WORKFLOW_RUN="$2"; shift 2 ;;
    --phase) [[ "$#" -ge 2 ]] || usage; PHASE="$2"; shift 2 ;;
    --receipt) [[ "$#" -ge 2 ]] || usage; RECEIPT="$2"; shift 2 ;;
    --rollback-from-sha) [[ "$#" -ge 2 ]] || usage; ROLLBACK_FROM_SHA="$2"; shift 2 ;;
    --rollback-target-sha) [[ "$#" -ge 2 ]] || usage; ROLLBACK_TARGET_SHA="$2"; shift 2 ;;
    *) usage ;;
  esac
done

[[ "$OWNER_PROJECT" =~ ^[a-z][a-z0-9_-]{1,31}$ ]] || { echo 'probe owner project is invalid' >&2; exit 64; }
[[ "$OWNER_REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo 'probe owner repository is invalid' >&2; exit 64; }
[[ "$OPERATION_SHA" =~ ^[a-f0-9]{40}$ ]] || { echo 'probe operation SHA must be 40 lowercase hex characters' >&2; exit 64; }
[[ "$RUNTIME_SHA" =~ ^[a-f0-9]{40}$ ]] || { echo 'probe runtime SHA must be 40 lowercase hex characters' >&2; exit 64; }
[[ "$WORKFLOW_RUN" =~ ^[1-9][0-9]*$ ]] || { echo 'probe workflow run is invalid' >&2; exit 64; }
case "$PHASE" in pre-mutation|pre-activation|post-activation|post-rollback|post-compensation) ;; *) echo 'probe phase is invalid' >&2; exit 64 ;; esac
if [[ -n "$ROLLBACK_FROM_SHA$ROLLBACK_TARGET_SHA" ]]; then
  [[ "$ROLLBACK_FROM_SHA" =~ ^[a-f0-9]{40}$ \
    && "$ROLLBACK_TARGET_SHA" =~ ^[a-f0-9]{40}$ ]] || {
    echo 'rollback probe metadata is invalid' >&2
    exit 64
  }
  [[ "$PHASE" == post-rollback || "$PHASE" == post-compensation ]] || {
    echo 'rollback metadata is forbidden for this probe phase' >&2
    exit 64
  }
else
  [[ "$PHASE" != post-rollback && "$PHASE" != post-compensation ]] || {
    echo 'rollback probe metadata is required' >&2
    exit 64
  }
fi
case "$PHASE" in
  post-activation)
    [[ "$RUNTIME_SHA" == "$OPERATION_SHA" ]] || { echo 'post-activation runtime SHA must equal operation SHA' >&2; exit 64; }
    ;;
  post-rollback)
    [[ "$ROLLBACK_FROM_SHA" != "$ROLLBACK_TARGET_SHA" && "$RUNTIME_SHA" == "$ROLLBACK_TARGET_SHA" ]] \
      || { echo 'post-rollback runtime or rollback metadata is inconsistent' >&2; exit 64; }
    ;;
  post-compensation)
    [[ "$ROLLBACK_FROM_SHA" != "$ROLLBACK_TARGET_SHA" && "$RUNTIME_SHA" == "$ROLLBACK_FROM_SHA" ]] \
      || { echo 'post-compensation runtime or rollback metadata is inconsistent' >&2; exit 64; }
    ;;
esac
[[ "$RECEIPT" == /* && "$RECEIPT" != *$'\n'* ]] || { echo 'probe receipt path must be absolute' >&2; exit 64; }
[[ ! -e "$RECEIPT" ]] || { echo 'probe receipt already exists' >&2; exit 73; }
command -v node >/dev/null 2>&1 || { echo 'probe requires node' >&2; exit 69; }

TEMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TEMP_DIR"; }
trap cleanup EXIT

validate_probe_url() {
  local url="$1" allowed_hosts="$2"
  PROBE_URL="$url" ALLOWED_HOSTS="$allowed_hosts" node --input-type=module <<'NODE'
import { isIP } from 'node:net';
const url = new URL(process.env.PROBE_URL);
const allowed = new Set(process.env.ALLOWED_HOSTS.split(','));
if (url.protocol !== 'https:' || url.username || url.password || url.port) process.exit(1);
if (isIP(url.hostname) || !allowed.has(url.hostname)) process.exit(1);
process.stdout.write(url.href);
NODE
}

resolve_probe_redirect() {
  local current_url="$1" location="$2" allowed_hosts="$3"
  CURRENT_URL="$current_url" LOCATION="$location" ALLOWED_HOSTS="$allowed_hosts" node --input-type=module <<'NODE'
import { isIP } from 'node:net';
const url = new URL(process.env.LOCATION, process.env.CURRENT_URL);
const allowed = new Set(process.env.ALLOWED_HOSTS.split(','));
if (url.protocol !== 'https:' || url.username || url.password || url.port) process.exit(1);
if (isIP(url.hostname) || !allowed.has(url.hostname)) process.exit(1);
process.stdout.write(url.href);
NODE
}

probe_url() {
  local name="$1" url="$2" allowed_hosts="$3" current_url status effective scheme
  local redirects=0 header_file location metadata
  current_url="$(validate_probe_url "$url" "$allowed_hosts")" || {
    printf 'failure\tconfigured_url_not_allowed\n'
    return 1
  }
  while (( redirects <= 5 )); do
    header_file="$TEMP_DIR/${name}-${redirects}.headers"
    # Each hop is an explicit GET; body, upload and HEAD flags are contractually forbidden.
    metadata="$(curl --silent --show-error --request GET --proto '=https' \
      --connect-timeout 5 --max-time 15 --output /dev/null --dump-header "$header_file" \
      --write-out '%{http_code}\t%{url_effective}\t%{scheme}' "$current_url" 2>/dev/null)" || {
      printf 'failure\thttps_request_failed\n'
      return 1
    }
    IFS=$'\t' read -r status effective scheme <<< "$metadata"
    [[ "$status" =~ ^[0-9]{3}$ && "$scheme" == https ]] || {
      printf 'failure\tinvalid_https_metadata\n'
      return 1
    }
    effective="$(validate_probe_url "$effective" "$allowed_hosts")" || {
      printf 'failure\teffective_url_not_allowed\n'
      return 1
    }
    if [[ "$status" =~ ^30[12378]$ ]]; then
      location="$(awk 'BEGIN { IGNORECASE=1 } /^Location:/ { sub(/\r$/, ""); sub(/^[^:]+:[[:space:]]*/, ""); value=$0 } END { print value }' "$header_file")"
      [[ -n "$location" ]] || { printf 'failure\tredirect_location_missing\n'; return 1; }
      current_url="$(resolve_probe_redirect "$effective" "$location" "$allowed_hosts")" || {
        printf 'failure\tredirect_target_not_allowed\n'
        return 1
      }
      redirects=$((redirects + 1))
      continue
    fi
    [[ "$status" == 200 ]] || { printf 'failure\thttp_status_%s\n' "$status"; return 1; }
    printf 'success\t%s\t%s\t%s\thttps\n' "$status" "$effective" "$redirects"
    return 0
  done
  printf 'failure\tredirect_budget_exceeded\n'
  return 1
}

if BLOG_RESULT="$(probe_url blog-public "$BLOG_URL" 'blog.blankhoney.xyz')"; then :; else :; fi
if BLOG_STATUS_RESULT="$(probe_url blog-public-status "$BLOG_STATUS_URL" 'blog.blankhoney.xyz')"; then :; else :; fi
if RSS_RESULT="$(probe_url rss-production-auth "$RSS_URL" 'ai-reader.blankhoney.xyz,auth.blankhoney.xyz')"; then :; else :; fi

capture_check() {
  local status_name="$1" error_code="$2"
  shift 2
  if "$@" >/dev/null 2>&1; then
    printf -v "$status_name" '%s' success
  else
    printf -v "$status_name" '%s' "$error_code"
  fi
}

if docker inspect "$CADDY_CONTAINER" > "$TEMP_DIR/caddy.json" 2>/dev/null; then
  CADDY_INSPECT_STATUS=success
else
  CADDY_INSPECT_STATUS=caddy_inspect_failed
fi
if docker network inspect myrss-app > "$TEMP_DIR/myrss-app.json" 2>/dev/null; then
  MYRSS_NETWORK_STATUS=success
else
  MYRSS_NETWORK_STATUS=myrss_network_inspect_failed
fi
if docker network inspect brianstorm-edge > "$TEMP_DIR/brianstorm-edge.json" 2>/dev/null; then
  BLOG_NETWORK_STATUS=success
else
  BLOG_NETWORK_STATUS=blog_network_inspect_failed
fi
capture_check CADDY_VALIDATE_STATUS caddy_config_validation_failed \
  docker exec "$CADDY_CONTAINER" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
if docker exec "$CADDY_CONTAINER" /bin/sh -ec \
  'wget -q -T 5 -O - http://127.0.0.1:2019/config/' > "$TEMP_DIR/active-caddy.json" 2>/dev/null; then
  ACTIVE_CONFIG_STATUS=success
else
  ACTIVE_CONFIG_STATUS=active_caddy_config_unavailable
fi
capture_check RSS_UPSTREAM_STATUS rss_upstream_unreachable \
  docker exec "$CADDY_CONTAINER" /bin/sh -ec 'wget -q -T 5 -O /dev/null http://web-prod:3000/'
capture_check BLOG_UPSTREAM_STATUS blog_upstream_unreachable \
  docker exec "$CADDY_CONTAINER" /bin/sh -ec 'wget -q -T 5 -O /dev/null http://brianstorm-web:3000/api/status'

mkdir -p "$(dirname "$RECEIPT")"
RECEIPT_TEMP="$(dirname "$RECEIPT")/.receipt-$$.tmp"
CONTRACT_VERSION="$CONTRACT_VERSION" OWNER_PROJECT="$OWNER_PROJECT" OWNER_REPO="$OWNER_REPO" \
OPERATION_SHA="$OPERATION_SHA" RUNTIME_SHA="$RUNTIME_SHA" WORKFLOW_RUN="$WORKFLOW_RUN" PHASE="$PHASE" \
ROLLBACK_FROM_SHA="$ROLLBACK_FROM_SHA" BLOG_URL="$BLOG_URL" \
ROLLBACK_TARGET_SHA="$ROLLBACK_TARGET_SHA" \
BLOG_STATUS_URL="$BLOG_STATUS_URL" RSS_URL="$RSS_URL" BLOG_RESULT="$BLOG_RESULT" \
BLOG_STATUS_RESULT="$BLOG_STATUS_RESULT" RSS_RESULT="$RSS_RESULT" \
CADDY_CONTAINER="$CADDY_CONTAINER" TEMP_DIR="$TEMP_DIR" \
CADDY_INSPECT_STATUS="$CADDY_INSPECT_STATUS" MYRSS_NETWORK_STATUS="$MYRSS_NETWORK_STATUS" \
BLOG_NETWORK_STATUS="$BLOG_NETWORK_STATUS" CADDY_VALIDATE_STATUS="$CADDY_VALIDATE_STATUS" \
ACTIVE_CONFIG_STATUS="$ACTIVE_CONFIG_STATUS" RSS_UPSTREAM_STATUS="$RSS_UPSTREAM_STATUS" \
BLOG_UPSTREAM_STATUS="$BLOG_UPSTREAM_STATUS" node --input-type=module > "$RECEIPT_TEMP" <<'NODE'
import { readFileSync } from 'node:fs';

function exactKeys(value, expected, label) {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) throw new Error(`${label}_shape_invalid`);
}
function parseCurl(name, configuredURL, raw) {
  const [result, statusRaw, finalURL, redirectsRaw, scheme] = raw.split('\t');
  if (result === 'failure') {
    const error = statusRaw;
    if (!/^[a-z0-9_]+$/.test(error)) throw new Error(`${name}_error_invalid`);
    return { name, configuredURL, status: null, finalURL: null, tls: false, redirect: false, result, error };
  }
  if (result !== 'success') throw new Error(`${name}_curl_result_invalid`);
  const status = Number(statusRaw);
  const redirects = Number(redirectsRaw);
  if (!Number.isSafeInteger(status) || !Number.isSafeInteger(redirects)) throw new Error(`${name}_curl_result_invalid`);
  const parsed = new URL(finalURL);
  if (parsed.protocol !== 'https:' || scheme !== 'https') throw new Error(`${name}_tls_invalid`);
  if (name.startsWith('blog-public') && (status !== 200 || redirects !== 0 || parsed.hostname !== 'blog.blankhoney.xyz')) {
    return { name, configuredURL, status, finalURL, tls: true, redirect: redirects > 0, result: 'failure', error: 'blog_public_contract_failed' };
  }
  if (!name.startsWith('blog-public') && (status !== 200 || redirects < 1 || parsed.hostname !== 'auth.blankhoney.xyz')) {
    return { name, configuredURL, status, finalURL, tls: true, redirect: redirects > 0, result: 'failure', error: 'rss_auth_redirect_contract_failed' };
  }
  return { name, configuredURL, status, finalURL, tls: true, redirect: redirects > 0, result, error: null };
}
const errors = [];
const check = (name) => {
  const value = process.env[name];
  if (value !== 'success') errors.push(value);
  return value === 'success';
};
const caddyInspectOk = check('CADDY_INSPECT_STATUS');
let networks = null;
if (caddyInspectOk) {
  try {
    const caddyList = JSON.parse(readFileSync(`${process.env.TEMP_DIR}/caddy.json`, 'utf8'));
    if (!Array.isArray(caddyList) || caddyList.length !== 1) throw new Error();
    networks = caddyList[0]?.NetworkSettings?.Networks;
    if (!networks || typeof networks !== 'object') throw new Error();
  } catch {
    errors.push('caddy_inspect_invalid');
  }
}
const readNetwork = (name) => {
  try {
    const value = JSON.parse(readFileSync(`${process.env.TEMP_DIR}/${name}.json`, 'utf8'));
    if (!Array.isArray(value) || value.length !== 1 || value[0].Name !== name) throw new Error();
    return value[0].Driver;
  } catch {
    errors.push(`${name.replaceAll('-', '_')}_inspect_invalid`);
    return null;
  }
};
const myrssDriver = check('MYRSS_NETWORK_STATUS') ? readNetwork('myrss-app') : null;
const blogDriver = check('BLOG_NETWORK_STATUS') ? readNetwork('brianstorm-edge') : null;
if ((myrssDriver && myrssDriver !== 'bridge') || (blogDriver && blogDriver !== 'bridge')) errors.push('shared_edge_driver_invalid');
const myrssAttached = Boolean(networks && Object.hasOwn(networks, 'myrss-app'));
const blogAttached = Boolean(networks && Object.hasOwn(networks, 'brianstorm-edge'));
if (networks && (!myrssAttached || !blogAttached)) errors.push('caddy_membership_invalid');
const configValidated = check('CADDY_VALIDATE_STATUS');
let configLoaded = false;
if (check('ACTIVE_CONFIG_STATUS')) {
  try {
    const activeConfig = JSON.stringify(JSON.parse(readFileSync(`${process.env.TEMP_DIR}/active-caddy.json`, 'utf8')));
    configLoaded = ['blog.blankhoney.xyz', 'brianstorm-web:3000', 'web-prod:3000'].every((value) => activeConfig.includes(value));
    if (!configLoaded) errors.push('active_caddy_config_invalid');
  } catch {
    errors.push('active_caddy_config_invalid');
  }
}
const rssUpstreamReachable = check('RSS_UPSTREAM_STATUS');
const blogUpstreamReachable = check('BLOG_UPSTREAM_STATUS');
const urls = [
  parseCurl('blog-public', process.env.BLOG_URL, process.env.BLOG_RESULT),
  parseCurl('blog-public-status', process.env.BLOG_STATUS_URL, process.env.BLOG_STATUS_RESULT),
  parseCurl('rss-production-auth', process.env.RSS_URL, process.env.RSS_RESULT),
];
for (const url of urls) if (url.result !== 'success') errors.push(url.error);
const overallStatus = errors.length === 0 ? 'success' : 'failure';
const receipt = {
  contractVersion: Number(process.env.CONTRACT_VERSION),
  owner: { project: process.env.OWNER_PROJECT, repo: process.env.OWNER_REPO },
  operation: { fullSha: process.env.OPERATION_SHA },
  workflowRun: Number(process.env.WORKFLOW_RUN),
  runtime: { fullSha: process.env.RUNTIME_SHA },
  rollback: {
    rollbackFrom: process.env.ROLLBACK_FROM_SHA || null,
    target: process.env.ROLLBACK_TARGET_SHA || null,
  },
  phase: process.env.PHASE,
  timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
  overallStatus,
  urls,
  edge: {
    caddyContainer: process.env.CADDY_CONTAINER,
    myrssAppAttached: myrssAttached,
    brianstormEdgeAttached: blogAttached,
    networkDriver: blogDriver,
    configLoaded: configValidated && configLoaded,
    rssUpstreamReachable,
    blogUpstreamReachable,
    result: overallStatus,
    error: errors.length ? [...new Set(errors)] : null,
  },
};
exactKeys(receipt, ['contractVersion', 'owner', 'operation', 'workflowRun', 'runtime', 'rollback', 'phase', 'timestamp', 'overallStatus', 'urls', 'edge'], 'receipt');
process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`);
NODE
chmod 600 "$RECEIPT_TEMP"
mv "$RECEIPT_TEMP" "$RECEIPT"
RECEIPT_STATUS="$(RECEIPT="$RECEIPT" node --input-type=module <<'NODE'
import { readFileSync } from 'node:fs';
const receipt = JSON.parse(readFileSync(process.env.RECEIPT, 'utf8'));
if (!['success', 'failure'].includes(receipt.overallStatus)) process.exit(1);
process.stdout.write(receipt.overallStatus);
NODE
)" || { echo 'shared edge receipt verification failed' >&2; exit 1; }
if [[ "$RECEIPT_STATUS" != success ]]; then
  printf 'shared edge contract v1 failure recorded for %s\n' "$PHASE" >&2
  exit 1
fi
printf 'shared edge contract v1 verified for %s\n' "$PHASE"
