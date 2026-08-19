#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Shared-VPS edge contract v1. This script is deliberately self-contained so
# RSS and Blog release transactions can call the same probe at every boundary.
# It never accepts caller-provided URLs: doing so would turn a release probe
# into an SSRF primitive.

set -euo pipefail

readonly CONTRACT_VERSION=1
readonly CADDY_CONTAINER='myrss-edge-caddy-1'
readonly MYRSS_NETWORK='myrss-app'
readonly BRIANSTORM_NETWORK='brianstorm-edge'
readonly BRIANSTORM_PRODUCTION_WEB='brianstorm-web'
readonly BRIANSTORM_STAGING_WEB='brianstorm-staging-web'
readonly RSS_URL='https://ai-reader.blankhoney.xyz/'
readonly BLOG_URL='https://blog.blankhoney.xyz/zh'
readonly CURL_CONNECT_TIMEOUT_SECONDS=10
readonly CURL_MAX_TIME_SECONDS=20
readonly CURL_MAX_REDIRECTS=5

owner_project=''
owner_repo=''
full_sha=''
workflow_run=''
phase=''
receipt_path=''

usage() {
    cat >&2 <<'EOF'
Usage:
  verify-shared-edge.sh \
    --owner-project <project> \
    --owner-repo <owner/repo> \
    --full-sha <40-lowercase-hex> \
    --workflow-run <positive-integer> \
    --phase <pre-mutation|post-activation|post-rollback|post-compensation> \
    --receipt <path>
EOF
}

die() {
    echo "shared-edge contract v${CONTRACT_VERSION}: $*" >&2
    exit 1
}

require_value() {
    local option="$1"
    local value="${2:-}"
    [[ -n "$value" ]] || die "$option requires a value"
}

while (( $# > 0 )); do
    case "$1" in
        --owner-project)
            require_value "$1" "${2:-}"
            owner_project="$2"
            shift 2
            ;;
        --owner-repo)
            require_value "$1" "${2:-}"
            owner_repo="$2"
            shift 2
            ;;
        --full-sha)
            require_value "$1" "${2:-}"
            full_sha="$2"
            shift 2
            ;;
        --workflow-run)
            require_value "$1" "${2:-}"
            workflow_run="$2"
            shift 2
            ;;
        --phase)
            require_value "$1" "${2:-}"
            phase="$2"
            shift 2
            ;;
        --receipt)
            require_value "$1" "${2:-}"
            receipt_path="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            usage
            die "unknown argument: $1"
            ;;
    esac
done

[[ "$owner_project" =~ ^[a-z][a-z0-9-]{1,63}$ ]] || die 'owner.project must be a lowercase project name'
[[ "$owner_repo" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$ ]] || die 'owner.repo must be a GitHub owner/repository pair'
[[ "$full_sha" =~ ^[0-9a-f]{40}$ ]] || die 'candidate.fullSha must be 40 lowercase hexadecimal characters'
[[ "$workflow_run" =~ ^[1-9][0-9]*$ ]] || die 'workflowRun must be a positive integer'
case "$phase" in
    pre-mutation|post-activation|post-rollback|post-compensation) ;;
    *) die 'phase must be pre-mutation, post-activation, post-rollback, or post-compensation' ;;
esac
[[ -n "$receipt_path" ]] || die 'receipt path is required'

command -v curl >/dev/null 2>&1 || die 'curl is required'
command -v docker >/dev/null 2>&1 || die 'docker is required'
command -v node >/dev/null 2>&1 || die 'node is required for JSON-safe Docker inspect parsing'

is_allowed_https_url() {
    local candidate="$1"
    node -e '
const value = process.argv[1];
try {
  const url = new URL(value);
  const allowed = new Set([
    "ai-reader.blankhoney.xyz",
    "auth.blankhoney.xyz",
    "blog.blankhoney.xyz",
  ]);
  const defaultHttpsPort = url.port === "" || url.port === "443";
  const noUserInfo = url.username === "" && url.password === "";
  process.exit(
    url.protocol === "https:"
      && allowed.has(url.hostname)
      && defaultHttpsPort
      && noUserInfo
      ? 0
      : 1
  );
} catch { process.exit(1); }
' "$candidate"
}

resolve_and_validate_redirect() {
    local current_url="$1"
    local redirect_url="$2"
    local resolved
    resolved="$(node -e '
const [base, value] = process.argv.slice(1);
try { process.stdout.write(new URL(value, base).toString()); }
catch { process.exit(1); }
' "$current_url" "$redirect_url")" || die 'redirect URL is malformed'
    is_allowed_https_url "$resolved" || die "redirect target is outside the fixed HTTPS allowlist: $resolved"
    printf '%s' "$resolved"
}

# The probe manually follows a small redirect chain rather than handing curl an
# unrestricted -L flow. Every target is validated against the fixed HTTPS
# allowlist before it is requested.
probe_https_get() {
    local name="$1"
    local configured_url="$2"
    local require_redirect="$3"
    local current_url="$configured_url"
    local redirects=0
    local initial_status=''
    local initial_redirect_url=''
    local status=''
    local redirect_url=''
    local tls_result=''
    local effective_url=''
    local response=''
    local final_url=''

    is_allowed_https_url "$configured_url" || die "internal error: configured $name URL is not allowlisted"

    while :; do
        response="$(curl \
            --silent \
            --show-error \
            --request GET \
            --proto '=https' \
            --connect-timeout "$CURL_CONNECT_TIMEOUT_SECONDS" \
            --max-time "$CURL_MAX_TIME_SECONDS" \
            --output /dev/null \
            --write-out '%{http_code}\n%{redirect_url}\n%{ssl_verify_result}\n%{url_effective}' \
            "$current_url")" || die "$name HTTPS GET failed for $current_url"
        status="${response%%$'\n'*}"
        response="${response#*$'\n'}"
        redirect_url="${response%%$'\n'*}"
        response="${response#*$'\n'}"
        tls_result="${response%%$'\n'*}"
        effective_url="${response#*$'\n'}"
        [[ "$status" =~ ^[1-5][0-9][0-9]$ ]] || die "$name returned an invalid HTTP status"
        [[ "$tls_result" == '0' ]] || die "$name TLS verification failed"

        if [[ -z "$initial_status" ]]; then
            initial_status="$status"
            initial_redirect_url="$redirect_url"
        fi

        if [[ "$status" =~ ^3[0-9][0-9]$ ]]; then
            (( redirects += 1 ))
            (( redirects <= CURL_MAX_REDIRECTS )) || die "$name exceeded the redirect limit"
            [[ -n "$redirect_url" ]] || die "$name returned a redirect without a Location target"
            current_url="$(resolve_and_validate_redirect "$current_url" "$redirect_url")"
            continue
        fi

        final_url="$effective_url"
        [[ -n "$final_url" ]] || die "$name did not report an effective HTTPS URL"
        is_allowed_https_url "$final_url" || die "$name final URL is outside the fixed HTTPS allowlist"
        break
    done

    if [[ "$name" == 'rss' ]]; then
        [[ "$initial_status" =~ ^3[0-9][0-9]$ ]] || die 'RSS must begin with an authentication redirect'
        (( redirects > 0 )) || die 'RSS authentication redirect was not followed'
        [[ "$status" == '200' ]] || die "RSS authentication destination returned HTTP $status, expected 200"
    else
        [[ "$require_redirect" == 'false' ]] || die 'internal error: Blog redirect contract must be false'
        [[ "$status" == '200' ]] || die "Blog public route returned HTTP $status, expected 200"
    fi

    NAME="$name" CONFIGURED_URL="$configured_url" STATUS="$status" FINAL_URL="$final_url" \
        REDIRECT_REQUIRED="$require_redirect" REDIRECT_FOLLOWED="$([[ "$redirects" -gt 0 ]] && echo true || echo false)" \
        INITIAL_STATUS="$initial_status" INITIAL_REDIRECT_URL="$initial_redirect_url" \
        node -e '
const redirect = {
  required: process.env.REDIRECT_REQUIRED === "true",
  followed: process.env.REDIRECT_FOLLOWED === "true",
  initialStatus: Number(process.env.INITIAL_STATUS),
  initialURL: process.env.INITIAL_REDIRECT_URL || null,
};
process.stdout.write(JSON.stringify({
  name: process.env.NAME,
  configuredURL: process.env.CONFIGURED_URL,
  status: Number(process.env.STATUS),
  finalURL: process.env.FINAL_URL,
  tls: true,
  redirect,
}));
'
}

parse_caddy_networks() {
    node -e '
let raw = "";
process.stdin.on("data", (chunk) => { raw += chunk; });
process.stdin.on("end", () => {
  try {
    const inspect = JSON.parse(raw);
    if (!Array.isArray(inspect) || inspect.length !== 1) throw new Error("expected exactly one inspect record");
    const networks = inspect[0]?.NetworkSettings?.Networks;
    if (!networks || typeof networks !== "object" || Array.isArray(networks)) throw new Error("missing network map");
    process.stdout.write(`${Boolean(networks["myrss-app"])}\t${Boolean(networks["brianstorm-edge"])}\n`);
  } catch (error) {
    console.error(`invalid Caddy docker inspect JSON: ${error.message}`);
    process.exit(1);
  }
});
'
}

parse_network_driver() {
    node -e '
let raw = "";
process.stdin.on("data", (chunk) => { raw += chunk; });
process.stdin.on("end", () => {
  try {
    const inspect = JSON.parse(raw);
    if (!Array.isArray(inspect) || inspect.length !== 1 || typeof inspect[0]?.Driver !== "string") throw new Error("missing Driver");
    process.stdout.write(inspect[0].Driver);
  } catch (error) {
    console.error(`invalid Docker network inspect JSON: ${error.message}`);
    process.exit(1);
  }
});
'
}

parse_member_of_production_edge() {
    node -e '
let raw = "";
process.stdin.on("data", (chunk) => { raw += chunk; });
process.stdin.on("end", () => {
  try {
    const inspect = JSON.parse(raw);
    if (!Array.isArray(inspect) || inspect.length !== 1) throw new Error("expected exactly one inspect record");
    const networks = inspect[0]?.NetworkSettings?.Networks;
    if (!networks || typeof networks !== "object" || Array.isArray(networks)) throw new Error("missing network map");
    process.stdout.write(String(Boolean(networks["brianstorm-edge"])));
  } catch (error) {
    console.error(`invalid container docker inspect JSON: ${error.message}`);
    process.exit(1);
  }
});
'
}

validate_active_caddy_config() {
    node -e '
let raw = "";
process.stdin.on("data", (chunk) => { raw += chunk; });
process.stdin.on("end", () => {
  const strings = (value, output = []) => {
    if (typeof value === "string") output.push(value);
    else if (Array.isArray(value)) value.forEach((item) => strings(item, output));
    else if (value && typeof value === "object") Object.values(value).forEach((item) => strings(item, output));
    return output;
  };
  const hostMatches = (route, host) => Array.isArray(route?.match)
    && route.match.some((matcher) => Array.isArray(matcher?.host) && matcher.host.includes(host));
  try {
    const config = JSON.parse(raw);
    if (!config || typeof config !== "object" || Array.isArray(config)) throw new Error("configuration root is not an object");
    const routes = [];
    const visit = (value) => {
      if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value === "object") {
        if (Array.isArray(value.match) && Array.isArray(value.handle)) routes.push(value);
        Object.values(value).forEach(visit);
      }
    };
    visit(config);
    const requireProductionRoute = (host, expectedUpstream, forbiddenUpstream) => {
      const candidates = routes.filter((route) => hostMatches(route, host));
      if (candidates.length === 0) throw new Error(`no active route matches ${host}`);
      const values = candidates.flatMap((route) => strings(route));
      if (!values.includes(expectedUpstream)) throw new Error(`${host} does not route to ${expectedUpstream}`);
      if (values.includes(forbiddenUpstream)) throw new Error(`${host} routes to forbidden ${forbiddenUpstream}`);
    };
    requireProductionRoute("ai-reader.blankhoney.xyz", "api-prod:8000", "api-staging:8000");
    requireProductionRoute("blog.blankhoney.xyz", "brianstorm-web:3000", "brianstorm-staging-web:3000");
  } catch (error) {
    console.error(`invalid active Caddy configuration: ${error.message}`);
    process.exit(1);
  }
});
'
}

caddy_inspect="$(docker inspect "$CADDY_CONTAINER")" || die "cannot inspect fixed Caddy container $CADDY_CONTAINER"
read -r myrss_app_attached brianstorm_edge_attached < <(printf '%s' "$caddy_inspect" | parse_caddy_networks) || die 'cannot parse Caddy network membership'
[[ "$myrss_app_attached" == 'true' ]] || die "Caddy is not attached to $MYRSS_NETWORK"
[[ "$brianstorm_edge_attached" == 'true' ]] || die "Caddy is not attached to $BRIANSTORM_NETWORK"

myrss_driver="$(docker network inspect "$MYRSS_NETWORK" | parse_network_driver)" || die "cannot parse $MYRSS_NETWORK driver"
brianstorm_driver="$(docker network inspect "$BRIANSTORM_NETWORK" | parse_network_driver)" || die "cannot parse $BRIANSTORM_NETWORK driver"
[[ "$myrss_driver" == 'bridge' ]] || die "$MYRSS_NETWORK must use the bridge driver"
[[ "$brianstorm_driver" == 'bridge' ]] || die "$BRIANSTORM_NETWORK must use the bridge driver"

production_blog_inspect="$(docker inspect "$BRIANSTORM_PRODUCTION_WEB")" || die "cannot inspect production Blog web container $BRIANSTORM_PRODUCTION_WEB"
production_blog_attached="$(printf '%s' "$production_blog_inspect" | parse_member_of_production_edge)" || die 'cannot parse production Blog network membership'
[[ "$production_blog_attached" == 'true' ]] || die "production Blog web is not attached to $BRIANSTORM_NETWORK"

staging_web_attached='false'
if staging_web_inspect="$(docker inspect "$BRIANSTORM_STAGING_WEB" 2>/dev/null)"; then
    staging_web_attached="$(printf '%s' "$staging_web_inspect" | parse_member_of_production_edge)" || die 'cannot parse staging Blog network membership'
fi
[[ "$staging_web_attached" == 'false' ]] || die "staging Blog web must never join production $BRIANSTORM_NETWORK"

docker exec "$CADDY_CONTAINER" caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null || die 'Caddyfile is not loadable in the fixed Caddy container'
active_caddy_config="$(docker exec "$CADDY_CONTAINER" sh -ec "wget -q -T $CURL_CONNECT_TIMEOUT_SECONDS -O - http://127.0.0.1:2019/config/")" || die 'cannot read the active Caddy Admin configuration'
printf '%s' "$active_caddy_config" | validate_active_caddy_config || die 'active Caddy configuration does not preserve production RSS and Blog routes'
docker exec "$CADDY_CONTAINER" sh -ec "wget -q -T $CURL_CONNECT_TIMEOUT_SECONDS -O /dev/null http://api-prod:8000/healthz" || die 'RSS production upstream is not reachable from Caddy'
docker exec "$CADDY_CONTAINER" sh -ec "wget -q -T $CURL_CONNECT_TIMEOUT_SECONDS -O /dev/null http://brianstorm-web:3000/zh" || die 'Blog production upstream is not reachable from Caddy'

rss_url_result="$(probe_https_get rss "$RSS_URL" true)"
blog_url_result="$(probe_https_get blog "$BLOG_URL" false)"
timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

receipt_dir="$(dirname "$receipt_path")"
[[ -d "$receipt_dir" ]] || die "receipt directory does not exist: $receipt_dir"
umask 077
receipt_tmp="$(mktemp "${receipt_path}.tmp.XXXXXX")"
cleanup_receipt_tmp() { rm -f -- "$receipt_tmp"; }
trap cleanup_receipt_tmp EXIT

RECEIPT_CONTRACT_VERSION="$CONTRACT_VERSION" OWNER_PROJECT="$owner_project" OWNER_REPO="$owner_repo" FULL_SHA="$full_sha" \
    WORKFLOW_RUN="$workflow_run" PHASE="$phase" TIMESTAMP="$timestamp" RSS_URL_RESULT="$rss_url_result" \
    BLOG_URL_RESULT="$blog_url_result" RECEIPT_CADDY_CONTAINER="$CADDY_CONTAINER" MYRSS_ATTACHED="$myrss_app_attached" \
    BRIANSTORM_ATTACHED="$brianstorm_edge_attached" MYRSS_DRIVER="$myrss_driver" BRIANSTORM_DRIVER="$brianstorm_driver" \
    PRODUCTION_BLOG_ATTACHED="$production_blog_attached" STAGING_WEB_ATTACHED="$staging_web_attached" \
    node -e '
const urlResults = [JSON.parse(process.env.RSS_URL_RESULT), JSON.parse(process.env.BLOG_URL_RESULT)];
const receipt = {
  contractVersion: Number(process.env.RECEIPT_CONTRACT_VERSION),
  owner: { project: process.env.OWNER_PROJECT, repo: process.env.OWNER_REPO },
  candidate: { fullSha: process.env.FULL_SHA },
  workflowRun: Number(process.env.WORKFLOW_RUN),
  phase: process.env.PHASE,
  timestamp: process.env.TIMESTAMP,
  urls: urlResults,
  edge: {
    caddyContainer: process.env.RECEIPT_CADDY_CONTAINER,
    myrssAppAttached: process.env.MYRSS_ATTACHED === "true",
    brianstormEdgeAttached: process.env.BRIANSTORM_ATTACHED === "true",
    networkDriver: {
      myrssApp: process.env.MYRSS_DRIVER,
      brianstormEdge: process.env.BRIANSTORM_DRIVER,
    },
    configLoaded: true,
    rssUpstreamReachable: true,
    blogUpstreamReachable: true,
    productionBlogWebAttachedToProductionEdge: process.env.PRODUCTION_BLOG_ATTACHED === "true",
    stagingWebAttachedToProductionEdge: process.env.STAGING_WEB_ATTACHED === "true",
  },
};
process.stdout.write(`${JSON.stringify(receipt)}\n`);
' > "$receipt_tmp"

mv -f -- "$receipt_tmp" "$receipt_path"
trap - EXIT
echo "shared-edge contract v${CONTRACT_VERSION} passed: $phase ($receipt_path)"
