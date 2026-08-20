#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const SHA = /^[a-f0-9]{40}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const DIGEST = /^sha256:[a-f0-9]{64}$/;
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const LOCK_ROOT = '/var/lib/reno-shared-vps/release-lock-v1';
const LOCK_PATH = `${LOCK_ROOT}/release.lock`;
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort());
const fail = (message) => { throw new Error(`Blog control-plane receipt rejected: ${message}`); };

export function verifyReceipt(receipt, expected) {
  if (!exact(receipt, ['contractVersion', 'event', 'owner', 'controlPlane', 'operation',
    'installer', 'source', 'installed', 'canonical', 'lock', 'probes', 'timestamp'])) fail('schema');
  if (!exact(receipt.owner, ['project', 'repo'])
      || !exact(receipt.controlPlane, ['repo', 'fullSha', 'workflowRun', 'workflowRunAttempt'])
      || !exact(receipt.operation, ['repo', 'fullSha', 'workflowRun', 'workflowRunAttempt',
        'artifactId', 'artifactDigest', 'webImageDigest', 'companionImageDigest'])
      || !exact(receipt.installer, ['repo', 'fullSha', 'workflowRun', 'workflowRunAttempt'])
      || !exact(receipt.source, ['rssSourceSha', 'installerTransactionSha256', 'wrapperSha256', 'coreSha256',
        'transactionSha256', 'probeSha256', 'probeVerifierSha256'])
      || !exact(receipt.installed, ['wrapperSha256', 'coreSha256', 'transactionSha256',
        'probeSha256', 'probeVerifierSha256'])
      || !exact(receipt.canonical, ['root', 'lockPath', 'lockDeviceInode', 'owner', 'group',
        'rootMode', 'lockMode', 'auditMode'])
      || !exact(receipt.lock, ['authority', 'tokenSha256', 'audit', 'acquiredAt'])
      || !exact(receipt.lock.audit, ['state', 'lastEvent'])
      || !exact(receipt.probes, ['before', 'after'])
      || !exact(receipt.probes.before, ['phase', 'receiptPath', 'sha256'])
      || !exact(receipt.probes.after, ['phase', 'receiptPath', 'sha256'])) fail('nested schema');
  const same = (actual, wanted, label) => { if (actual !== wanted) fail(label); };
  same(receipt.contractVersion, 2, 'version');
  same(receipt.event, 'blog-control-plane-installed', 'event');
  same(receipt.owner.project, 'rss', 'owner project');
  same(receipt.owner.repo, 'blankhoney/reno_rss', 'owner repo');
  same(receipt.controlPlane.repo, expected.repo, 'control repo');
  same(receipt.controlPlane.fullSha, expected.controlSha, 'control SHA');
  same(receipt.controlPlane.workflowRun, Number(expected.controlRun), 'control run');
  same(receipt.controlPlane.workflowRunAttempt, Number(expected.controlAttempt), 'control attempt');
  same(receipt.operation.repo, expected.repo, 'operation repo');
  same(receipt.operation.fullSha, expected.operationSha, 'operation SHA');
  same(receipt.operation.workflowRun, Number(expected.producerRun), 'producer run');
  same(receipt.operation.workflowRunAttempt, Number(expected.producerAttempt), 'producer attempt');
  same(receipt.operation.artifactId, Number(expected.artifactId), 'artifact ID');
  same(receipt.operation.artifactDigest, expected.artifactDigest, 'artifact digest');
  same(receipt.operation.webImageDigest, expected.webDigest, 'web digest');
  same(receipt.operation.companionImageDigest, expected.companionDigest, 'companion digest');
  same(receipt.installer.repo, 'blankhoney/reno_rss', 'installer repo');
  same(receipt.installer.fullSha, expected.installerSha, 'installer SHA');
  same(receipt.installer.workflowRun, Number(expected.installerRun), 'installer run');
  same(receipt.installer.workflowRunAttempt, Number(expected.installerAttempt), 'installer attempt');
  same(receipt.source.rssSourceSha, expected.rssSourceSha, 'RSS source');
  same(receipt.source.installerTransactionSha256, expected.installerTransactionSha, 'installer transaction hash');
  if (!SHA256.test(receipt.source.installerTransactionSha256)) fail('installer transaction hash shape');
  for (const name of ['wrapperSha256', 'coreSha256', 'transactionSha256', 'probeSha256', 'probeVerifierSha256']) {
    if (!SHA256.test(receipt.source[name]) || receipt.installed[name] !== receipt.source[name]) fail(`${name} drift`);
  }
  same(receipt.source.wrapperSha256, expected.wrapperSha, 'wrapper hash');
  same(receipt.source.coreSha256, expected.coreSha, 'core hash');
  same(receipt.source.transactionSha256, expected.transactionSha, 'transaction hash');
  same(receipt.source.probeSha256, expected.probeSha, 'probe hash');
  same(receipt.source.probeVerifierSha256, expected.probeVerifierSha, 'probe verifier hash');
  same(receipt.canonical.root, LOCK_ROOT, 'lock root');
  same(receipt.canonical.lockPath, LOCK_PATH, 'lock path');
  if (!/^\d+:\d+$/.test(receipt.canonical.lockDeviceInode)) fail('lock inode');
  if (JSON.stringify({...receipt.canonical, lockDeviceInode: ''}) !== JSON.stringify({
    root: LOCK_ROOT, lockPath: LOCK_PATH, lockDeviceInode: '', owner: 'root', group: 'reno-deploy',
    rootMode: '0770', lockMode: '0660', auditMode: '0770'})) fail('canonical attributes');
  if (receipt.lock.authority !== 'live-flock' || !SHA256.test(receipt.lock.tokenSha256)
      || receipt.lock.audit.state !== 'held' || receipt.lock.audit.lastEvent !== 'acquired'
      || !RFC3339.test(receipt.lock.acquiredAt)) fail('lock evidence');
  for (const [position, phase] of [['before', 'pre-mutation'], ['after', 'pre-activation']]) {
    const probe = receipt.probes[position];
    if (probe.phase !== phase || !SHA256.test(probe.sha256)
        || !new RegExp(`^${LOCK_ROOT}/audit/blog-control-plane-v2-[1-9][0-9]*-[1-9][0-9]*-${position}\\.json$`).test(probe.receiptPath)) fail(`${position} probe`);
  }
  if (!RFC3339.test(receipt.timestamp)) fail('timestamp');
  if (![receipt.controlPlane.fullSha, receipt.operation.fullSha, receipt.installer.fullSha].every((value) => SHA.test(value))
      || ![receipt.operation.artifactDigest, receipt.operation.webImageDigest,
        receipt.operation.companionImageDigest].every((value) => DIGEST.test(value))) fail('identity shape');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv.length !== 24) {
    console.error('usage: verify-blog-control-plane-install-receipt.mjs RECEIPT REPO CONTROL_SHA CONTROL_RUN CONTROL_ATTEMPT OPERATION_SHA PRODUCER_RUN PRODUCER_ATTEMPT ARTIFACT_ID ARTIFACT_DIGEST WEB_DIGEST COMPANION_DIGEST INSTALLER_RUN INSTALLER_ATTEMPT RSS_SOURCE_SHA INSTALLER_SHA WRAPPER CORE TRANSACTION PROBE PROBE_VERIFIER');
    process.exit(64);
  }
  try {
    const [file, repo, controlSha, controlRun, controlAttempt, operationSha, producerRun,
      producerAttempt, artifactId, artifactDigest, webDigest, companionDigest, installerRun,
      installerAttempt, rssSourceSha, installerSha, wrapperSha, coreSha, transactionSha,
      probeSha, probeVerifierSha, installerTransactionSha] = process.argv.slice(2);
    verifyReceipt(JSON.parse(readFileSync(file, 'utf8')), { repo, controlSha, controlRun,
      controlAttempt, operationSha, producerRun, producerAttempt, artifactId, artifactDigest,
      webDigest, companionDigest, installerRun, installerAttempt, rssSourceSha, installerSha,
      wrapperSha, coreSha, transactionSha, probeSha, probeVerifierSha, installerTransactionSha });
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exit(64);
  }
}
