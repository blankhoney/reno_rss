import assert from 'node:assert/strict';
import { mkdtemp, chmod, readFile, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';

const repoRoot = path.resolve(import.meta.dirname, '../../..');
const probe = path.join(repoRoot, 'infra/deploy/verify-shared-edge.sh');
const sha = 'a'.repeat(40);
const rollbackFrom = 'b'.repeat(40);
const rollbackTarget = 'c'.repeat(40);
const currentRuntime = 'd'.repeat(40);

async function fixture(overrides = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'shared-edge-probe-'));
  const bin = path.join(root, 'bin');
  const receipt = path.join(root, 'receipt.json');
  await writeFile(path.join(root, 'docker'), `#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "inspect" ]]; then
  case "$2" in
    myrss-edge-caddy-1) printf '%s\\n' "\${FAKE_CADDY_JSON}" ;;
    brianstorm-web) printf '%s\\n' "\${FAKE_BLOG_JSON}" ;;
    brianstorm-staging-web)
      if [[ -n "\${FAKE_STAGING_JSON:-}" ]]; then printf '%s\\n' "\$FAKE_STAGING_JSON"; else exit 1; fi
      ;;
    *) exit 1 ;;
  esac
  exit 0
elif [[ "$1" == "network" && "$2" == "inspect" ]]; then
  case "$3" in
    myrss-app) printf '[{"Driver":"%s"}]\\n' "\${FAKE_MYRSS_DRIVER:-bridge}" ;;
    brianstorm-edge) printf '[{"Driver":"%s"}]\\n' "\${FAKE_BRIANSTORM_DRIVER:-bridge}" ;;
    *) exit 1 ;;
  esac
  exit 0
elif [[ "$1" == "exec" ]]; then
  args="$*"
  if [[ "$args" == *'caddy adapt'* ]]; then [[ "\${FAKE_CONFIG_FAIL:-0}" != 1 ]] || exit 1; exit 0; fi
  if [[ "$args" == *'127.0.0.1:2019/config/'* ]]; then printf '%s\\n' "\${FAKE_ACTIVE_CADDY_CONFIG}"; exit 0; fi
  if [[ "$args" == *'api-prod:8000/healthz'* ]]; then [[ "\${FAKE_RSS_UPSTREAM_FAIL:-0}" != 1 ]] || exit 1; exit 0; fi
  if [[ "$args" == *'brianstorm-web:3000/zh'* ]]; then [[ "\${FAKE_BLOG_UPSTREAM_FAIL:-0}" != 1 ]] || exit 1; exit 0; fi
  exit 1
fi
exit 1
`);
  await writeFile(path.join(root, 'curl'), `#!/usr/bin/env bash
set -euo pipefail
args="$*"
url="\${!#}"
if [[ "$url" == 'https://blog.blankhoney.xyz/zh' ]]; then
  printf '%s\\n%s\\n%s\\n%s\\n' "\${FAKE_BLOG_STATUS:-200}" "" "\${FAKE_BLOG_TLS:-0}" "\${FAKE_BLOG_FINAL_URL:-https://blog.blankhoney.xyz/zh}"
  exit 0
fi
if [[ "$url" == 'https://ai-reader.blankhoney.xyz/' ]]; then
  printf '%s\\n%s\\n%s\\n%s\\n' "\${FAKE_RSS_INITIAL_STATUS:-302}" "\${FAKE_RSS_REDIRECT_URL:-https://auth.blankhoney.xyz/?rd=https%3A%2F%2Fai-reader.blankhoney.xyz%2F}" "\${FAKE_RSS_TLS:-0}" "https://ai-reader.blankhoney.xyz/"
  exit 0
fi
if [[ "$url" == https://auth.blankhoney.xyz/* ]]; then
  printf '%s\\n%s\\n%s\\n%s\\n' "\${FAKE_RSS_FINAL_STATUS:-200}" "" "\${FAKE_RSS_TLS:-0}" "\${FAKE_RSS_FINAL_URL:-https://auth.blankhoney.xyz/?rd=https%3A%2F%2Fai-reader.blankhoney.xyz%2F}"
  exit 0
fi
exit 1
`);
  await chmod(path.join(root, 'docker'), 0o755);
  await chmod(path.join(root, 'curl'), 0o755);
  await writeFile(path.join(root, 'placeholder'), '');
  await rm(path.join(root, 'placeholder'));
  await (await import('node:fs/promises')).mkdir(bin);
  await (await import('node:fs/promises')).rename(path.join(root, 'docker'), path.join(bin, 'docker'));
  await (await import('node:fs/promises')).rename(path.join(root, 'curl'), path.join(bin, 'curl'));

  const caddyNetworks = overrides.caddyNetworks ?? { 'myrss-app': {}, 'brianstorm-edge': {} };
  const blogNetworks = overrides.blogNetworks ?? { 'brianstorm-edge': {} };
  const activeConfig = overrides.activeConfig ?? {
    apps: { http: { servers: { srv0: { routes: [
      { match: [{ host: ['ai-reader.blankhoney.xyz'] }], handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: 'api-prod:8000' }] }] },
      { match: [{ host: ['blog.blankhoney.xyz'] }], handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: 'brianstorm-web:3000' }] }] },
    ] } } } },
  };
  const env = {
    ...process.env,
    PATH: `${bin}:${process.env.PATH}`,
    FAKE_CADDY_JSON: JSON.stringify([{ NetworkSettings: { Networks: caddyNetworks } }]),
    FAKE_BLOG_JSON: JSON.stringify([{ NetworkSettings: { Networks: blogNetworks } }]),
    FAKE_ACTIVE_CADDY_CONFIG: JSON.stringify(activeConfig),
    ...overrides.env,
  };

  return {
    receipt,
    root,
    run(extra = [], phase = 'pre-mutation', runtimeSha = undefined) {
      const isRollbackPhase = phase === 'post-rollback' || phase === 'post-compensation';
      const runtimeTarget = runtimeSha ?? (phase === 'post-rollback' ? rollbackTarget
        : phase === 'post-compensation' ? rollbackFrom
          : sha);
      return spawnSync('bash', [probe,
        '--owner-project', 'rss',
        '--owner-repo', 'blankhoney/reno_rss',
        '--operation-sha', sha,
        '--workflow-run', '32292226657',
        '--phase', phase,
        '--runtime-sha', runtimeTarget,
        ...(isRollbackPhase ? [
          '--rollback-from-sha', rollbackFrom,
          '--rollback-target-sha', rollbackTarget,
        ] : []),
        '--receipt', receipt,
        ...extra,
      ], { cwd: repoRoot, env, encoding: 'utf8' });
    },
    async cleanup() { await rm(root, { recursive: true, force: true }); },
  };
}

test('transaction fixture preserves operation/runtime values at every release boundary', async () => {
  const item = await fixture();
  try {
    const phases = [
      { phase: 'pre-mutation', runtimeSha: currentRuntime },
      { phase: 'pre-activation', runtimeSha: currentRuntime },
      { phase: 'post-activation', runtimeSha: sha },
      { phase: 'post-rollback', runtimeSha: rollbackTarget },
      { phase: 'post-compensation', runtimeSha: rollbackFrom },
    ];
    for (const { phase, runtimeSha } of phases) {
      const result = item.run([], phase, runtimeSha);
      assert.equal(result.status, 0, result.stderr || result.stdout);
      const receipt = JSON.parse(await readFile(item.receipt, 'utf8'));
      assert.deepEqual(receipt.owner, { project: 'rss', repo: 'blankhoney/reno_rss' });
      assert.deepEqual(receipt.operation, { fullSha: sha });
      assert.deepEqual(Object.keys(receipt).sort(), isRollbackPhase(phase)
        ? ['contractVersion', 'edge', 'operation', 'owner', 'phase', 'rollback', 'runtime', 'timestamp', 'urls', 'workflowRun']
        : ['contractVersion', 'edge', 'operation', 'owner', 'phase', 'runtime', 'timestamp', 'urls', 'workflowRun']);
      assert.deepEqual(Object.keys(receipt.edge).sort(), [
        'blogUpstreamReachable',
        'brianstormEdgeAttached',
        'caddyContainer',
        'configLoaded',
        'myrssAppAttached',
        'networkDriver',
        'productionBlogWebAttachedToProductionEdge',
        'rssUpstreamReachable',
        'stagingWebAttachedToProductionEdge',
      ]);
      assert.deepEqual(Object.keys(receipt.edge.networkDriver).sort(), ['brianstormEdge', 'myrssApp']);
      for (const url of receipt.urls) {
        assert.deepEqual(Object.keys(url).sort(), ['configuredURL', 'finalURL', 'name', 'redirect', 'status', 'tls']);
        assert.deepEqual(Object.keys(url.redirect).sort(), ['followed', 'initialStatus', 'initialURL', 'required']);
      }
      assert.equal(receipt.contractVersion, 1);
      assert.equal(receipt.workflowRun, 32292226657);
      assert.equal(receipt.phase, phase);
      assert.deepEqual(receipt.runtime, { fullSha: runtimeSha });
      if (isRollbackPhase(phase)) {
        assert.deepEqual(receipt.rollback, { rollbackFrom, target: rollbackTarget });
      }
      assert.match(receipt.timestamp, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
      assert.equal(receipt.urls.length, 2);
      assert.equal(receipt.urls.find((entry) => entry.name === 'rss').redirect.required, true);
      assert.equal(receipt.urls.find((entry) => entry.name === 'blog').status, 200);
      assert.equal(receipt.edge.caddyContainer, 'myrss-edge-caddy-1');
      assert.equal(receipt.edge.myrssAppAttached, true);
      assert.equal(receipt.edge.brianstormEdgeAttached, true);
      assert.equal(receipt.edge.networkDriver.myrssApp, 'bridge');
      assert.equal(receipt.edge.networkDriver.brianstormEdge, 'bridge');
      assert.equal(receipt.edge.configLoaded, true);
      assert.equal(receipt.edge.rssUpstreamReachable, true);
      assert.equal(receipt.edge.blogUpstreamReachable, true);
      assert.equal(receipt.edge.stagingWebAttachedToProductionEdge, false);
    }
  } finally {
    await item.cleanup();
  }
});

test('rejects malformed or unknown CLI inputs before a receipt can be accepted', async () => {
  const item = await fixture();
  try {
    for (const args of [
      ['--operation-sha', 'abc'],
      ['--runtime-sha', 'abc'],
      ['--full-sha', sha],
      ['--runtime-target-sha', sha],
      ['--sha', sha],
      ['--phase', 'after-lunch'],
      ['--phase', 'post-rollback'],
      ['--phase', 'post-rollback', '--runtime-sha', sha],
      ['--phase', 'post-rollback', '--runtime-sha', rollbackFrom],
      ['--phase', 'post-compensation', '--runtime-sha', rollbackTarget],
      ['--phase', 'post-activation', '--runtime-sha', rollbackTarget],
      ['--rollback-from-sha', rollbackFrom],
      ['--unexpected', 'value'],
    ]) {
      const result = item.run(args);
      assert.notEqual(result.status, 0);
      await assert.rejects(readFile(item.receipt));
    }
  } finally {
    await item.cleanup();
  }
});

test('fails closed without a success receipt for public, edge, driver, config, upstream, or staging-contamination failure', async () => {
  const cases = [
    { env: { FAKE_BLOG_STATUS: '503' } },
    { env: { FAKE_RSS_TLS: '1' } },
    { caddyNetworks: { 'myrss-app': {} } },
    { caddyNetworks: { 'brianstorm-edge': {} } },
    { env: { FAKE_MYRSS_DRIVER: 'overlay' } },
    { env: { FAKE_CONFIG_FAIL: '1' } },
    { activeConfig: {} },
    { env: { FAKE_ACTIVE_CADDY_CONFIG: '{not-json' } },
    { activeConfig: { apps: { http: { servers: { srv0: { routes: [
      { match: [{ host: ['ai-reader.blankhoney.xyz'] }], handle: [{ upstreams: [{ dial: 'api-prod:8000' }] }] },
      { match: [{ host: ['blog.blankhoney.xyz'] }], handle: [{ upstreams: [{ dial: 'brianstorm-web:3000' }, { dial: 'brianstorm-staging-web:3000' }] }] },
    ] } } } } } },
    { activeConfig: { apps: { http: { servers: { srv0: { routes: [
      { match: [{ host: ['ai-reader.blankhoney.xyz'] }], handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: 'api-prod:8000' }] }] },
      { match: [{ host: ['blog.blankhoney.xyz'] }], handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: 'brianstorm-web:3000' }] }] },
      { match: [{ host: ['staging.blog.blankhoney.xyz'] }], handle: [{ handler: 'reverse_proxy', upstreams: [{ dial: 'brianstorm-staging-web:3000' }] }] },
    ] } } } } } },
    { env: { FAKE_RSS_UPSTREAM_FAIL: '1' } },
    { env: { FAKE_BLOG_UPSTREAM_FAIL: '1' } },
    { env: { FAKE_STAGING_JSON: JSON.stringify([{ NetworkSettings: { Networks: { 'brianstorm-edge': {} } } }]) } },
  ];
  for (const options of cases) {
    const item = await fixture(options);
    try {
      const result = item.run();
      assert.notEqual(result.status, 0, result.stdout);
      await assert.rejects(readFile(item.receipt));
    } finally {
      await item.cleanup();
    }
  }
});

test('records an existing runtime separately before activation, then requires the operation SHA after activation', async () => {
  const item = await fixture();
  try {
    const before = item.run([], 'pre-activation', currentRuntime);
    assert.equal(before.status, 0, before.stderr || before.stdout);
    const preActivationReceipt = JSON.parse(await readFile(item.receipt, 'utf8'));
    assert.deepEqual(preActivationReceipt.operation, { fullSha: sha });
    assert.deepEqual(preActivationReceipt.runtime, { fullSha: currentRuntime });

    const mismatchedPostActivation = item.run([], 'post-activation', rollbackFrom);
    assert.notEqual(mismatchedPostActivation.status, 0);
    assert.match(mismatchedPostActivation.stderr, /post-activation runtime\.fullSha must equal operation\.fullSha/);
  } finally {
    await item.cleanup();
  }
});

function isRollbackPhase(phase) {
  return phase === 'post-rollback' || phase === 'post-compensation';
}

test('rejects unsafe redirect targets and a production edge without the production Blog web member', async () => {
  for (const target of [
    'https://attacker.example/',
    'https://user@auth.blankhoney.xyz/',
    'https://auth.blankhoney.xyz:4443/',
    'https://127.0.0.1/',
  ]) {
    const unsafeRedirect = await fixture({ env: { FAKE_RSS_REDIRECT_URL: target } });
    try {
      assert.notEqual(unsafeRedirect.run().status, 0);
      await assert.rejects(readFile(unsafeRedirect.receipt));
    } finally { await unsafeRedirect.cleanup(); }
  }

  const wrongBlogNetwork = await fixture({ blogNetworks: { 'brianstorm-staging-edge': {} } });
  try {
    assert.notEqual(wrongBlogNetwork.run().status, 0);
    await assert.rejects(readFile(wrongBlogNetwork.receipt));
  } finally { await wrongBlogNetwork.cleanup(); }
});
