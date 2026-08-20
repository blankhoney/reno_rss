#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
#
# Idempotently restore the fixed shared Caddy container's membership on the RSS
# and Blog production edge networks. This script never creates networks and
# never connects or disconnects an application container; those lifecycles stay
# owned by their respective projects.

set -euo pipefail

readonly CADDY_CONTAINER='myrss-edge-caddy-1'
readonly MYRSS_NETWORK='myrss-app'
readonly BRIANSTORM_NETWORK='brianstorm-edge'
readonly BRIANSTORM_PRODUCTION_WEB='brianstorm-web'
readonly BRIANSTORM_STAGING_WEB='brianstorm-staging-web'

die() {
    printf '%s\n' "shared-edge recovery: $*" >&2
    exit 1
}

(( $# == 0 )) || die 'this fixed contract accepts no arguments'
command -v docker >/dev/null 2>&1 || die 'docker is required'
command -v node >/dev/null 2>&1 || die 'node is required for strict inspect parsing'

parse_network_driver() {
    node -e '
let raw = "";
process.stdin.on("data", (chunk) => { raw += chunk; });
process.stdin.on("end", () => {
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value) || value.length !== 1 || typeof value[0]?.Driver !== "string") {
      throw new Error("expected one network inspect record with Driver");
    }
    process.stdout.write(value[0].Driver);
  } catch (error) {
    console.error(`invalid network inspect JSON: ${error.message}`);
    process.exit(1);
  }
});
'
}

container_has_network() {
    local network="$1"
    node -e '
const network = process.argv[1];
let raw = "";
process.stdin.on("data", (chunk) => { raw += chunk; });
process.stdin.on("end", () => {
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value) || value.length !== 1) throw new Error("expected one container inspect record");
    const networks = value[0]?.NetworkSettings?.Networks;
    if (!networks || typeof networks !== "object" || Array.isArray(networks)) throw new Error("missing network map");
    process.stdout.write(String(Object.hasOwn(networks, network)));
  } catch (error) {
    console.error(`invalid container inspect JSON: ${error.message}`);
    process.exit(1);
  }
});
' "$network"
}

network_driver() {
    local network="$1"
    local inspect
    inspect="$(docker network inspect "$network")" || die "required network does not exist: $network"
    printf '%s' "$inspect" | parse_network_driver || die "cannot parse network driver: $network"
}

inspect_membership() {
    local container="$1"
    local network="$2"
    local inspect
    inspect="$(docker inspect "$container")" || die "required container does not exist: $container"
    printf '%s' "$inspect" | container_has_network "$network" || die "cannot parse $container network membership"
}

myrss_driver="$(network_driver "$MYRSS_NETWORK")"
brianstorm_driver="$(network_driver "$BRIANSTORM_NETWORK")"
[[ "$myrss_driver" == 'bridge' ]] || die "$MYRSS_NETWORK must use the bridge driver"
[[ "$brianstorm_driver" == 'bridge' ]] || die "$BRIANSTORM_NETWORK must use the bridge driver"

production_blog_attached="$(inspect_membership "$BRIANSTORM_PRODUCTION_WEB" "$BRIANSTORM_NETWORK")"
[[ "$production_blog_attached" == 'true' ]] || die "production Blog web is not attached to $BRIANSTORM_NETWORK"

if staging_inspect="$(docker inspect "$BRIANSTORM_STAGING_WEB" 2>/dev/null)"; then
    staging_blog_attached="$(printf '%s' "$staging_inspect" | container_has_network "$BRIANSTORM_NETWORK")" \
        || die 'cannot parse staging Blog network membership'
    [[ "$staging_blog_attached" == 'false' ]] \
        || die "staging Blog web must never join production $BRIANSTORM_NETWORK"
fi

ensure_caddy_membership() {
    local network="$1"
    local attached
    attached="$(inspect_membership "$CADDY_CONTAINER" "$network")"
    if [[ "$attached" == 'true' ]]; then
        return 0
    fi

    if ! docker network connect "$network" "$CADDY_CONTAINER"; then
        # Another idempotent recovery may have won the race. Re-inspect before
        # deciding whether the transaction must fail closed.
        attached="$(inspect_membership "$CADDY_CONTAINER" "$network")"
        [[ "$attached" == 'true' ]] || die "cannot attach $CADDY_CONTAINER to $network"
    fi

    attached="$(inspect_membership "$CADDY_CONTAINER" "$network")"
    [[ "$attached" == 'true' ]] || die "$CADDY_CONTAINER is still detached from $network"
}

ensure_caddy_membership "$MYRSS_NETWORK"
ensure_caddy_membership "$BRIANSTORM_NETWORK"

echo "shared-edge recovery passed: $CADDY_CONTAINER is attached to $MYRSS_NETWORK and $BRIANSTORM_NETWORK"
