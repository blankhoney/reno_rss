import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { access, mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve(import.meta.dirname, '..');
const probe = path.join(root, 'verify-shared-edge.sh');
const verifier = path.join(root, 'verify-shared-edge-receipt.mjs');
const operation = '89abcdef0123456789abcdef0123456789abcdef';
const previous = '0123456789abcdef0123456789abcdef01234567';

async function fixture(overrides = {}) {
  const temp = await mkdtemp(path.join(os.tmpdir(), 'rss-shared-edge-'));
  const bin = path.join(temp, 'bin');
  const receipt = path.join(temp, 'receipt.json');
  await mkdir(bin);
  await writeFile(path.join(bin, 'curl'), `#!/usr/bin/env bash
set -euo pipefail
header=''; previous=''; method=''
for argument in "$@"; do
  [[ "$previous" != --dump-header ]] || header="$argument"
  [[ "$previous" != --request ]] || method="$argument"
  case "$argument" in --head|-I|--data|--data-*|-d|--form|-F|--upload-file|-T) exit 89;; esac
  previous="$argument"
done
[[ -n "$header" && "$method" == GET ]] || exit 90
url="\${!#}"
case "$url" in
  https://blog.blankhoney.xyz/zh) : > "$header"; printf '%s\t%s\t%s' "\${BLOG_STATUS:-200}" https://blog.blankhoney.xyz/zh https;;
  https://blog.blankhoney.xyz/api/status) : > "$header"; printf '%s\t%s\t%s' 200 https://blog.blankhoney.xyz/api/status https;;
  https://ai-reader.blankhoney.xyz/) printf '%s\n' 'HTTP/2 302' "Location: \${RSS_FINAL:-https://auth.blankhoney.xyz/}" > "$header"; printf '%s\t%s\t%s' 302 https://ai-reader.blankhoney.xyz/ https;;
  https://auth.blankhoney.xyz/) : > "$header"; printf '%s\t%s\t%s' 200 https://auth.blankhoney.xyz/ https;;
  *) exit 91;;
esac
`, { mode: 0o700 });
  await writeFile(path.join(bin, 'docker'), `#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == 'inspect myrss-edge-caddy-1' ]]; then
  printf '%s\n' '[{"NetworkSettings":{"Networks":{"myrss-app":{},"brianstorm-edge":{}}}}]'
elif [[ "$1 $2" == 'network inspect' ]]; then
  printf '[{"Name":"%s","Driver":"%s"}]\n' "$3" "\${NETWORK_DRIVER:-bridge}"
elif [[ "$1" == exec && "$3" == caddy && "$4" == validate ]]; then
  [[ "\${CONFIG_OK:-yes}" == yes ]]
elif [[ "$1" == exec && "$3" == /bin/sh ]]; then
  case "$*" in
    *127.0.0.1:2019/config*) printf '%s\n' '{"routes":["blog.blankhoney.xyz","brianstorm-web:3000","web-prod:3000"]}';;
    *brianstorm-web*|*web-prod*) exit 0;;
    *) exit 92;;
  esac
else exit 93
fi
`, { mode: 0o700 });
  return { receipt, env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, ...overrides } };
}

function run(fx, phase, runtime = operation, extra = []) {
  return spawnSync('bash', [probe,
    '--owner-project', 'rss', '--owner-repo', 'blankhoney/reno_rss',
    '--operation-sha', operation, '--runtime-sha', runtime,
    '--workflow-run', '32315969870', '--phase', phase,
    '--receipt', fx.receipt, ...extra,
  ], { encoding: 'utf8', env: fx.env });
}

function verify(fx, status, phase, runtime = operation, rollback = []) {
  return spawnSync('node', [verifier, fx.receipt, status, 'rss', 'blankhoney/reno_rss',
    operation, runtime, '32315969870', phase, ...rollback,
  ], { encoding: 'utf8' });
}

test('success receipt uses the byte-shared v1 schema and all canonical phases', async () => {
  for (const phase of ['pre-mutation', 'pre-activation', 'post-activation']) {
    const fx = await fixture();
    const runtime = phase === 'post-activation' ? operation : previous;
    assert.equal(run(fx, phase, runtime).status, 0, phase);
    assert.equal(verify(fx, 'success', phase, runtime).status, 0, phase);
  }
  for (const phase of ['post-rollback', 'post-compensation']) {
    const fx = await fixture();
    const runtime = phase === 'post-rollback' ? operation : previous;
    const rollback = [previous, operation];
    assert.equal(run(fx, phase, runtime, ['--rollback-from-sha', previous, '--rollback-target-sha', operation]).status, 0);
    assert.equal(verify(fx, 'success', phase, runtime, rollback).status, 0);
  }
});

test('operational failures are authenticated receipts; invalid identity writes nothing', async () => {
  for (const environment of [{ BLOG_STATUS: '503' }, { RSS_FINAL: 'https://127.0.0.1/' }, { NETWORK_DRIVER: 'nfs' }, { CONFIG_OK: 'no' }]) {
    const fx = await fixture(environment);
    assert.notEqual(run(fx, 'pre-mutation', previous).status, 0);
    assert.equal(verify(fx, 'failure', 'pre-mutation', previous).status, 0);
    assert.equal(JSON.parse(await readFile(fx.receipt, 'utf8')).overallStatus, 'failure');
  }
  const invalid = await fixture();
  assert.notEqual(run(invalid, 'unknown', previous).status, 0);
  await assert.rejects(() => access(invalid.receipt));
  assert.notEqual(spawnSync('bash', [probe, '--url', 'https://evil.example'], { env: invalid.env }).status, 0);
});

test('probe is bounded GET without automatic redirects and verifier rejects tampering', async () => {
  const source = await readFile(probe, 'utf8');
  assert.match(source, /--proto '=https'/);
  assert.match(source, /--request GET/);
  assert.doesNotMatch(source, /--location\b/);
  const fx = await fixture();
  assert.equal(run(fx, 'post-activation').status, 0);
  const receipt = JSON.parse(await readFile(fx.receipt, 'utf8'));
  receipt.runtime.fullSha = previous;
  await writeFile(fx.receipt, `${JSON.stringify(receipt)}\n`);
  assert.notEqual(verify(fx, 'success', 'post-activation').status, 0);
});
