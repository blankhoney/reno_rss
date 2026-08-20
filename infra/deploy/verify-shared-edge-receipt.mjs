#!/usr/bin/env node
import { isIP } from 'node:net';
import { readFileSync } from 'node:fs';

function fail(message) {
  process.stderr.write(`shared edge receipt rejected: ${message}\n`);
  process.exit(1);
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${label}_shape`);
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) fail(`${label}_shape`);
}

function validSha(value) {
  return typeof value === 'string' && /^[a-f0-9]{40}$/.test(value);
}

const [
  receiptPath,
  expectedStatus,
  ownerProject,
  ownerRepo,
  operationSha,
  runtimeSha,
  workflowRunRaw,
  phase,
  rollbackFromSha = '',
  rollbackTargetSha = '',
] = process.argv.slice(2);

if (![8, 10].includes(process.argv.slice(2).length)) fail('usage');
if (!['success', 'failure'].includes(expectedStatus)) fail('expected_status');
if (!/^[a-z][a-z0-9_-]{1,31}$/.test(ownerProject ?? '')) fail('owner_project');
if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(ownerRepo ?? '')) fail('owner_repo');
if (!validSha(operationSha) || !validSha(runtimeSha)) fail('sha');
if (!/^[1-9][0-9]*$/.test(workflowRunRaw ?? '')) fail('workflow_run');
if (!['pre-mutation', 'pre-activation', 'post-activation', 'post-rollback', 'post-compensation'].includes(phase)) fail('phase');
const rollbackExpected = rollbackFromSha !== '' || rollbackTargetSha !== '';
if (rollbackExpected && ![rollbackFromSha, rollbackTargetSha].every(validSha)) fail('rollback_metadata');
if ((phase === 'post-rollback' || phase === 'post-compensation') !== rollbackExpected) fail('rollback_phase');
if (phase === 'post-activation' && runtimeSha !== operationSha) fail('post_activation_runtime');
if (phase === 'post-rollback' && (rollbackFromSha === rollbackTargetSha || runtimeSha !== rollbackTargetSha)) fail('post_rollback_runtime');
if (phase === 'post-compensation' && (rollbackFromSha === rollbackTargetSha || runtimeSha !== rollbackFromSha)) fail('post_compensation_runtime');

let receipt;
try {
  receipt = JSON.parse(readFileSync(receiptPath, 'utf8'));
} catch {
  fail('unreadable');
}

exactKeys(receipt, ['contractVersion', 'owner', 'operation', 'workflowRun', 'runtime', 'rollback', 'phase', 'timestamp', 'overallStatus', 'urls', 'edge'], 'receipt');
exactKeys(receipt.owner, ['project', 'repo'], 'owner');
exactKeys(receipt.operation, ['fullSha'], 'operation');
exactKeys(receipt.runtime, ['fullSha'], 'runtime');
exactKeys(receipt.rollback, ['rollbackFrom', 'target'], 'rollback');
if (receipt.contractVersion !== 1) fail('contract_version');
if (receipt.owner.project !== ownerProject || receipt.owner.repo !== ownerRepo) fail('owner_identity');
if (receipt.operation.fullSha !== operationSha || receipt.workflowRun !== Number(workflowRunRaw)) fail('operation_identity');
if (receipt.runtime.fullSha !== runtimeSha || receipt.phase !== phase) fail('runtime_identity');
if (receipt.overallStatus !== expectedStatus) fail('overall_status');
if (typeof receipt.timestamp !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(receipt.timestamp)) fail('timestamp');
const expectedRollback = rollbackExpected
  ? { rollbackFrom: rollbackFromSha, target: rollbackTargetSha }
  : { rollbackFrom: null, target: null };
if (JSON.stringify(receipt.rollback) !== JSON.stringify(expectedRollback)) fail('rollback_identity');

const urlContract = new Map([
  ['blog-public', { configuredURL: 'https://blog.blankhoney.xyz/zh', hosts: new Set(['blog.blankhoney.xyz']) }],
  ['blog-public-status', { configuredURL: 'https://blog.blankhoney.xyz/api/status', hosts: new Set(['blog.blankhoney.xyz']) }],
  ['rss-production-auth', { configuredURL: 'https://ai-reader.blankhoney.xyz/', hosts: new Set(['ai-reader.blankhoney.xyz', 'auth.blankhoney.xyz']) }],
]);
if (!Array.isArray(receipt.urls) || receipt.urls.length !== urlContract.size) fail('urls_shape');
const seenNames = new Set();
for (const item of receipt.urls) {
  exactKeys(item, ['name', 'configuredURL', 'status', 'finalURL', 'tls', 'redirect', 'result', 'error'], 'url');
  const contract = urlContract.get(item.name);
  if (!contract || seenNames.has(item.name) || item.configuredURL !== contract.configuredURL) fail('url_identity');
  seenNames.add(item.name);
  if (!['success', 'failure'].includes(item.result)) fail('url_result');
  if (typeof item.tls !== 'boolean' || typeof item.redirect !== 'boolean') fail('url_types');
  if (item.result === 'success') {
    if (item.status !== 200 || item.tls !== true || item.error !== null || typeof item.finalURL !== 'string') fail('url_success');
    let parsed;
    try { parsed = new URL(item.finalURL); } catch { fail('url_final'); }
    if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port || isIP(parsed.hostname) || !contract.hosts.has(parsed.hostname)) fail('url_final');
    if (item.name.startsWith('blog-public') && item.redirect !== false) fail('blog_redirect');
    if (item.name === 'rss-production-auth' && (item.redirect !== true || parsed.hostname !== 'auth.blankhoney.xyz')) fail('rss_redirect');
  } else {
    const statusValid = item.status === null || (Number.isSafeInteger(item.status) && item.status >= 100 && item.status <= 599);
    const finalValid = item.finalURL === null || typeof item.finalURL === 'string';
    if (!statusValid || !finalValid || item.error === null || !/^[a-z0-9_]+$/.test(item.error)) fail('url_failure');
    if (item.finalURL !== null) {
      let parsed;
      try { parsed = new URL(item.finalURL); } catch { fail('url_failure_final'); }
      if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.port
        || isIP(parsed.hostname) || !contract.hosts.has(parsed.hostname)) fail('url_failure_final');
    }
  }
}
if (seenNames.size !== urlContract.size || [...urlContract.keys()].some((name) => !seenNames.has(name))) fail('urls_missing');

exactKeys(receipt.edge, [
  'caddyContainer', 'myrssAppAttached', 'brianstormEdgeAttached', 'networkDriver',
  'configLoaded', 'rssUpstreamReachable', 'blogUpstreamReachable', 'result', 'error',
], 'edge');
if (receipt.edge.caddyContainer !== 'myrss-edge-caddy-1' || receipt.edge.result !== expectedStatus) fail('edge_identity');
if (expectedStatus === 'success') {
  if (receipt.urls.some((item) => item.result !== 'success')) fail('success_urls');
  if (receipt.edge.error !== null || receipt.edge.networkDriver !== 'bridge'
    || receipt.edge.myrssAppAttached !== true || receipt.edge.brianstormEdgeAttached !== true
    || receipt.edge.configLoaded !== true || receipt.edge.rssUpstreamReachable !== true
    || receipt.edge.blogUpstreamReachable !== true) fail('success_edge');
} else {
  if (!Array.isArray(receipt.edge.error) || receipt.edge.error.length === 0
    || receipt.edge.error.some((value) => typeof value !== 'string' || !/^[a-z0-9_]+$/.test(value))) fail('failure_edge');
}

process.stdout.write(`shared edge ${expectedStatus} receipt verified\n`);
