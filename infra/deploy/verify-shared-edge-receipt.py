#!/usr/bin/env python3
"""Strict shared-edge receipt verifier using only the Python standard library."""
from __future__ import annotations

import ipaddress
import json
import re
import sys
import urllib.parse
from pathlib import Path

SHA = re.compile(r'^[a-f0-9]{40}$')
RFC3339 = re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
PHASES = {'pre-mutation', 'pre-activation', 'post-activation', 'post-rollback', 'post-compensation'}
URLS = {
    'blog-public': ('https://blog.blankhoney.xyz/zh', {'blog.blankhoney.xyz'}),
    'blog-public-status': ('https://blog.blankhoney.xyz/api/status', {'blog.blankhoney.xyz'}),
    'rss-production-auth': ('https://ai-reader.blankhoney.xyz/', {'ai-reader.blankhoney.xyz', 'auth.blankhoney.xyz'}),
}


def exact(value: object, keys: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f'{label}_shape')
    return value


def safe_url(value: str, hosts: set[str]) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port is not None:
        raise ValueError('url_transport')
    if parsed.hostname not in hosts:
        raise ValueError('url_host')
    try:
        ipaddress.ip_address(parsed.hostname or '')
    except ValueError:
        return parsed
    raise ValueError('url_ip')


def verify(receipt: object, expected: dict[str, object]) -> None:
    value = exact(receipt, {'contractVersion', 'owner', 'operation', 'workflowRun', 'runtime',
        'rollback', 'phase', 'timestamp', 'overallStatus', 'urls', 'edge'}, 'receipt')
    owner = exact(value['owner'], {'project', 'repo'}, 'owner')
    operation = exact(value['operation'], {'fullSha'}, 'operation')
    runtime = exact(value['runtime'], {'fullSha'}, 'runtime')
    rollback = exact(value['rollback'], {'rollbackFrom', 'target'}, 'rollback')
    if value['contractVersion'] != 1 or owner != {'project': expected['ownerProject'], 'repo': expected['ownerRepo']}:
        raise ValueError('owner_identity')
    if operation['fullSha'] != expected['operationSha'] or value['workflowRun'] != expected['workflowRun']:
        raise ValueError('operation_identity')
    if runtime['fullSha'] != expected['runtimeSha'] or value['phase'] != expected['phase']:
        raise ValueError('runtime_identity')
    if value['overallStatus'] != expected['status'] or not RFC3339.fullmatch(value['timestamp']):
        raise ValueError('status_timestamp')
    if rollback != expected['rollback']:
        raise ValueError('rollback_identity')
    if type(value['urls']) is not list or len(value['urls']) != len(URLS):
        raise ValueError('urls_shape')
    seen = set()
    for item_raw in value['urls']:
        item = exact(item_raw, {'name', 'configuredURL', 'status', 'finalURL', 'tls', 'redirect', 'result', 'error'}, 'url')
        if item['name'] not in URLS or item['name'] in seen:
            raise ValueError('url_identity')
        seen.add(item['name'])
        configured, hosts = URLS[item['name']]
        if item['configuredURL'] != configured or item['result'] not in {'success', 'failure'}:
            raise ValueError('url_contract')
        if item['finalURL'] is not None:
            safe_url(item['finalURL'], hosts)
        if item['result'] == 'success':
            if item['status'] != 200 or item['tls'] is not True or item['error'] is not None:
                raise ValueError('url_success')
            final = safe_url(item['finalURL'], hosts)
            if item['name'].startswith('blog-public') and item['redirect'] is not False:
                raise ValueError('blog_redirect')
            if item['name'] == 'rss-production-auth' and (item['redirect'] is not True or final.hostname != 'auth.blankhoney.xyz'):
                raise ValueError('rss_redirect')
        elif type(item['error']) is not str or not re.fullmatch(r'[a-z0-9_]+', item['error']):
            raise ValueError('url_failure')
        if item['result'] == 'failure':
            if item['status'] is not None and (type(item['status']) is not int or not 100 <= item['status'] <= 599):
                raise ValueError('url_failure_status')
            if item['finalURL'] is not None and type(item['finalURL']) is not str:
                raise ValueError('url_failure_final')
        if type(item['tls']) is not bool or type(item['redirect']) is not bool:
            raise ValueError('url_types')
    if seen != set(URLS):
        raise ValueError('urls_missing')
    edge = exact(value['edge'], {'caddyContainer', 'myrssAppAttached', 'brianstormEdgeAttached',
        'networkDriver', 'configLoaded', 'rssUpstreamReachable', 'blogUpstreamReachable', 'result', 'error'}, 'edge')
    if edge['caddyContainer'] != 'myrss-edge-caddy-1' or edge['result'] != expected['status']:
        raise ValueError('edge_identity')
    if expected['status'] == 'success':
        if edge != {'caddyContainer': 'myrss-edge-caddy-1', 'myrssAppAttached': True,
                'brianstormEdgeAttached': True, 'networkDriver': 'bridge', 'configLoaded': True,
                'rssUpstreamReachable': True, 'blogUpstreamReachable': True,
                'result': 'success', 'error': None}:
            raise ValueError('success_edge')
    elif (type(edge['error']) is not list or not edge['error']
            or any(type(item) is not str or not re.fullmatch(r'[a-z0-9_]+', item) for item in edge['error'])):
        raise ValueError('failure_edge')


def parse_expected(values: list[str]) -> tuple[Path, dict[str, object]]:
    if len(values) not in {8, 10}:
        raise ValueError('usage')
    receipt, status, project, repo, operation, runtime, workflow, phase, *rollback_values = values
    if status not in {'success', 'failure'} or phase not in PHASES or not SHA.fullmatch(operation) or not SHA.fullmatch(runtime):
        raise ValueError('arguments')
    if not re.fullmatch(r'[1-9][0-9]*', workflow):
        raise ValueError('workflow')
    rollback_expected = phase in {'post-rollback', 'post-compensation'}
    if rollback_expected != (len(rollback_values) == 2) or any(not SHA.fullmatch(item) for item in rollback_values):
        raise ValueError('rollback')
    rollback = {'rollbackFrom': rollback_values[0], 'target': rollback_values[1]} if rollback_values else {'rollbackFrom': None, 'target': None}
    if phase == 'post-activation' and runtime != operation:
        raise ValueError('post_activation')
    if phase == 'post-rollback' and (rollback['rollbackFrom'] == rollback['target'] or runtime != rollback['target']):
        raise ValueError('post_rollback')
    if phase == 'post-compensation' and (rollback['rollbackFrom'] == rollback['target'] or runtime != rollback['rollbackFrom']):
        raise ValueError('post_compensation')
    return Path(receipt), {'status': status, 'ownerProject': project, 'ownerRepo': repo,
        'operationSha': operation, 'runtimeSha': runtime, 'workflowRun': int(workflow), 'phase': phase,
        'rollback': rollback}


def main(values: list[str]) -> int:
    receipt_path, expected = parse_expected(values)
    verify(json.loads(receipt_path.read_text()), expected)
    print(f"shared edge {expected['status']} receipt verified")
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as error:
        print(f'shared edge receipt rejected: {type(error).__name__}:{error}', file=sys.stderr)
        raise SystemExit(1)
