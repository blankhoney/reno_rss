import assert from 'node:assert/strict';
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const ensure = path.join(repoRoot, 'infra/deploy/ensure-shared-edge.sh');

async function fixture({
  caddyNetworks = ['myrss-app'],
  myrssDriver = 'bridge',
  brianstormDriver = 'bridge',
  brianstormNetworkExists = true,
  productionBlogNetworks = ['brianstorm-edge'],
  stagingBlogNetworks = [],
  rssUpstream = true,
  blogUpstream = true,
} = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'ensure-shared-edge-'));
  const bin = path.join(root, 'bin');
  const state = path.join(root, 'caddy-networks.txt');
  const calls = path.join(root, 'docker-calls.txt');
  await mkdir(bin);
  await writeFile(state, `${caddyNetworks.join('\n')}\n`);
  await writeFile(calls, '');
  await writeFile(path.join(bin, 'docker'), `#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$FAKE_DOCKER_CALLS"
container_json() {
  local file="$1"
  node -e '
const fs = require("node:fs");
const names = fs.readFileSync(process.argv[1], "utf8").split(/\\n/).filter(Boolean);
const networks = Object.fromEntries(names.map((name) => [name, {}]));
process.stdout.write(JSON.stringify([{NetworkSettings:{Networks:networks}}]));
' "$file"
}
case "$1" in
  inspect)
    case "$2" in
      myrss-edge-caddy-1) container_json "$FAKE_CADDY_STATE" ;;
      brianstorm-web)
        FAKE_NAMES="$FAKE_PRODUCTION_BLOG_NETWORKS" node -e '
const names = process.env.FAKE_NAMES.split(",").filter(Boolean);
process.stdout.write(JSON.stringify([{NetworkSettings:{Networks:Object.fromEntries(names.map((name)=>[name,{}]))}}]));
' ;;
      brianstorm-staging-web)
        if [[ -z "$FAKE_STAGING_BLOG_NETWORKS" ]]; then exit 1; fi
        FAKE_NAMES="$FAKE_STAGING_BLOG_NETWORKS" node -e '
const names = process.env.FAKE_NAMES.split(",").filter(Boolean);
process.stdout.write(JSON.stringify([{NetworkSettings:{Networks:Object.fromEntries(names.map((name)=>[name,{}]))}}]));
' ;;
      *) exit 1 ;;
    esac
    ;;
  network)
    case "$2:$3" in
      inspect:myrss-app) printf '[{"Driver":"%s"}]\\n' "$FAKE_MYRSS_DRIVER" ;;
      inspect:brianstorm-edge)
        [[ "$FAKE_BRIANSTORM_NETWORK_EXISTS" == 1 ]] || exit 1
        printf '[{"Driver":"%s"}]\\n' "$FAKE_BRIANSTORM_DRIVER"
        ;;
      connect:*)
        network="$3"
        container="$4"
        [[ "$container" == myrss-edge-caddy-1 ]] || exit 91
        grep -Fxq "$network" "$FAKE_CADDY_STATE" || printf '%s\\n' "$network" >> "$FAKE_CADDY_STATE"
        ;;
      *) exit 1 ;;
    esac
    ;;
  exec)
    case "$*" in
      *web-prod*) [[ "$FAKE_RSS_UPSTREAM" == 1 ]] ;;
      *brianstorm-web*) [[ "$FAKE_BLOG_UPSTREAM" == 1 ]] ;;
      *) exit 1 ;;
    esac
    ;;
  *) exit 1 ;;
esac
`);
  await chmod(path.join(bin, 'docker'), 0o755);

  const env = {
    ...process.env,
    PATH: `${bin}:${process.env.PATH}`,
    FAKE_CADDY_STATE: state,
    FAKE_DOCKER_CALLS: calls,
    FAKE_MYRSS_DRIVER: myrssDriver,
    FAKE_BRIANSTORM_DRIVER: brianstormDriver,
    FAKE_BRIANSTORM_NETWORK_EXISTS: brianstormNetworkExists ? '1' : '0',
    FAKE_PRODUCTION_BLOG_NETWORKS: productionBlogNetworks.join(','),
    FAKE_STAGING_BLOG_NETWORKS: stagingBlogNetworks.join(','),
    FAKE_RSS_UPSTREAM: rssUpstream ? '1' : '0',
    FAKE_BLOG_UPSTREAM: blogUpstream ? '1' : '0',
  };

  return {
    root,
    calls,
    state,
    run() {
      return spawnSync('python3', [ensure], { cwd: repoRoot, env, encoding: 'utf8' });
    },
    async cleanup() { await rm(root, { recursive: true, force: true }); },
  };
}

test('idempotently restores only the fixed Caddy membership on both shared bridge networks', async () => {
  const item = await fixture();
  try {
    const first = item.run();
    assert.equal(first.status, 0, first.stderr || first.stdout);
    const second = item.run();
    assert.equal(second.status, 0, second.stderr || second.stdout);
    const calls = await readFile(item.calls, 'utf8');
    assert.equal(calls.match(/^network connect brianstorm-edge myrss-edge-caddy-1$/gm)?.length, 1);
    assert.equal(calls.includes('network connect myrss-app myrss-edge-caddy-1'), false);
    assert.equal(calls.includes('network connect brianstorm-edge brianstorm-web'), false);
    assert.equal(calls.includes('network connect brianstorm-edge brianstorm-staging-web'), false);
    assert.deepEqual((await readFile(item.state, 'utf8')).trim().split('\n').sort(), ['brianstorm-edge', 'myrss-app']);
    assert.doesNotMatch(await readFile(ensure, 'utf8'), /\bnode\b/);
  } finally { await item.cleanup(); }
});

test('fails closed before connection when either network is missing or has the wrong driver', async () => {
  for (const options of [
    { brianstormNetworkExists: false },
    { myrssDriver: 'overlay' },
    { brianstormDriver: 'overlay' },
    { rssUpstream: false },
    { blogUpstream: false },
  ]) {
    const item = await fixture(options);
    try {
      const result = item.run();
      assert.notEqual(result.status, 0);
      if (options.rssUpstream !== false && options.blogUpstream !== false) {
        assert.equal((await readFile(item.calls, 'utf8')).includes('network connect'), false);
      }
    } finally { await item.cleanup(); }
  }
});

test('refuses a production edge missing production Blog or contaminated by staging Blog', async () => {
  for (const options of [
    { productionBlogNetworks: [] },
    { stagingBlogNetworks: ['brianstorm-edge'] },
  ]) {
    const item = await fixture(options);
    try {
      const result = item.run();
      assert.notEqual(result.status, 0);
      assert.equal((await readFile(item.calls, 'utf8')).includes('network connect'), false);
    } finally { await item.cleanup(); }
  }
});
