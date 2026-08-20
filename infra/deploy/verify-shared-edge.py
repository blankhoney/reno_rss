#!/usr/bin/env python3
"""Fail-closed shared-edge probe using Python 3 standard library plus Docker CLI."""
from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

CONTRACT_VERSION = 1
CADDY = 'myrss-edge-caddy-1'
URLS = (
    ('blog-public', 'https://blog.blankhoney.xyz/zh', {'blog.blankhoney.xyz'}, False),
    ('blog-public-status', 'https://blog.blankhoney.xyz/api/status', {'blog.blankhoney.xyz'}, False),
    ('rss-production-auth', 'https://ai-reader.blankhoney.xyz/', {'ai-reader.blankhoney.xyz', 'auth.blankhoney.xyz'}, True),
)
SHA = re.compile(r'^[a-f0-9]{40}$')
PHASES = {'pre-mutation', 'pre-activation', 'post-activation', 'post-rollback', 'post-compensation'}


def verifier_module():
    path = Path(__file__).with_name('verify-shared-edge-receipt.py')
    spec = importlib.util.spec_from_file_location('shared_edge_receipt', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('receipt_verifier_load')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def probe_url(name: str, configured: str, hosts: set[str], require_redirect: bool) -> dict:
    module = verifier_module()
    current = configured
    redirects = 0
    status = None
    try:
        while redirects <= 5:
            parsed = module.safe_url(current, hosts)
            target = urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
            connection = http.client.HTTPSConnection(parsed.hostname, 443,
                timeout=15, context=ssl.create_default_context())
            try:
                connection.request('GET', target, headers={'User-Agent': 'reno-shared-edge-v1'})
                response = connection.getresponse()
                status = response.status
                response.read(1024 * 1024)
                location = response.getheader('Location')
            finally:
                connection.close()
            if status in {301, 302, 303, 307, 308}:
                if not location:
                    raise RuntimeError('redirect_location_missing')
                current = urllib.parse.urljoin(current, location)
                module.safe_url(current, hosts)
                redirects += 1
                continue
            if status != 200:
                raise RuntimeError(f'http_status_{status}')
            final = module.safe_url(current, hosts)
            if require_redirect and (redirects < 1 or final.hostname != 'auth.blankhoney.xyz'):
                raise RuntimeError('rss_auth_redirect_contract_failed')
            if not require_redirect and redirects != 0:
                raise RuntimeError('blog_public_contract_failed')
            return {'name': name, 'configuredURL': configured, 'status': status, 'finalURL': current,
                'tls': True, 'redirect': redirects > 0, 'result': 'success', 'error': None}
        raise RuntimeError('redirect_budget_exceeded')
    except Exception as error:
        code = str(error) if re.fullmatch(r'[a-z0-9_]+', str(error)) else 'https_request_failed'
        return {'name': name, 'configuredURL': configured, 'status': status, 'finalURL': None,
            'tls': False, 'redirect': redirects > 0, 'result': 'failure', 'error': code}


def command(*values: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(values, check=False, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=15)


def docker_json(*values: str) -> object:
    result = command('docker', *values, capture=True)
    if result.returncode != 0 or len(result.stdout) > 4 * 1024 * 1024:
        raise RuntimeError('docker_inspect_failed')
    return json.loads(result.stdout)


def edge_state(errors: list[str]) -> dict:
    networks = {}
    driver = None
    try:
        caddy = docker_json('inspect', CADDY)
        if type(caddy) is not list or len(caddy) != 1:
            raise ValueError()
        networks = caddy[0]['NetworkSettings']['Networks']
        if type(networks) is not dict:
            raise ValueError()
    except Exception:
        errors.append('caddy_inspect_invalid')
    for network in ('myrss-app', 'brianstorm-edge'):
        try:
            value = docker_json('network', 'inspect', network)
            if type(value) is not list or len(value) != 1 or value[0]['Name'] != network:
                raise ValueError()
            current_driver = value[0]['Driver']
            if current_driver != 'bridge':
                errors.append('shared_edge_driver_invalid')
            if network == 'brianstorm-edge':
                driver = current_driver
        except Exception:
            errors.append(f"{network.replace('-', '_')}_inspect_invalid")
    myrss = 'myrss-app' in networks
    blog = 'brianstorm-edge' in networks
    if networks and (not myrss or not blog):
        errors.append('caddy_membership_invalid')
    config_valid = command('docker', 'exec', CADDY, 'caddy', 'validate', '--config',
        '/etc/caddy/Caddyfile', '--adapter', 'caddyfile').returncode == 0
    active = command('docker', 'exec', CADDY, '/bin/sh', '-ec',
        'wget -q -T 5 -O - http://127.0.0.1:2019/config/', capture=True)
    config_loaded = False
    if config_valid and active.returncode == 0:
        try:
            raw = json.dumps(json.loads(active.stdout))
            config_loaded = all(value in raw for value in
                ('blog.blankhoney.xyz', 'brianstorm-web:3000', 'web-prod:3000'))
        except Exception:
            pass
    if not config_loaded:
        errors.append('active_caddy_config_invalid')
    rss = command('docker', 'exec', CADDY, '/bin/sh', '-ec',
        'wget -q -T 5 -O /dev/null http://web-prod:3000/').returncode == 0
    blog_upstream = command('docker', 'exec', CADDY, '/bin/sh', '-ec',
        'wget -q -T 5 -O /dev/null http://brianstorm-web:3000/api/status').returncode == 0
    if not rss:
        errors.append('rss_upstream_unreachable')
    if not blog_upstream:
        errors.append('blog_upstream_unreachable')
    return {'caddyContainer': CADDY, 'myrssAppAttached': myrss,
        'brianstormEdgeAttached': blog, 'networkDriver': driver, 'configLoaded': config_loaded,
        'rssUpstreamReachable': rss, 'blogUpstreamReachable': blog_upstream}


def arguments(values: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    for name in ('owner-project', 'owner-repo', 'operation-sha', 'runtime-sha', 'workflow-run', 'phase', 'receipt'):
        parser.add_argument(f'--{name}', required=True)
    parser.add_argument('--rollback-from-sha', default='')
    parser.add_argument('--rollback-target-sha', default='')
    args = parser.parse_args(values)
    if not re.fullmatch(r'[a-z][a-z0-9_-]{1,31}', args.owner_project):
        raise ValueError('owner_project')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.owner_repo):
        raise ValueError('owner_repo')
    if not SHA.fullmatch(args.operation_sha) or not SHA.fullmatch(args.runtime_sha):
        raise ValueError('sha')
    if not re.fullmatch(r'[1-9][0-9]*', args.workflow_run) or args.phase not in PHASES:
        raise ValueError('workflow_phase')
    rollback = bool(args.rollback_from_sha or args.rollback_target_sha)
    if rollback != (args.phase in {'post-rollback', 'post-compensation'}):
        raise ValueError('rollback_phase')
    if rollback and (not SHA.fullmatch(args.rollback_from_sha) or not SHA.fullmatch(args.rollback_target_sha)):
        raise ValueError('rollback_sha')
    if args.phase == 'post-activation' and args.runtime_sha != args.operation_sha:
        raise ValueError('post_activation')
    if args.phase == 'post-rollback' and (args.rollback_from_sha == args.rollback_target_sha or args.runtime_sha != args.rollback_target_sha):
        raise ValueError('post_rollback')
    if args.phase == 'post-compensation' and (args.rollback_from_sha == args.rollback_target_sha or args.runtime_sha != args.rollback_from_sha):
        raise ValueError('post_compensation')
    receipt = Path(args.receipt)
    if not receipt.is_absolute() or receipt.exists() or not receipt.parent.is_dir():
        raise ValueError('receipt_path')
    return args


def main(values: list[str]) -> int:
    args = arguments(values)
    urls = [probe_url(*contract) for contract in URLS]
    errors = [item['error'] for item in urls if item['result'] != 'success']
    edge = edge_state(errors)
    status = 'success' if not errors else 'failure'
    edge.update({'result': status, 'error': None if not errors else list(dict.fromkeys(errors))})
    rollback = {'rollbackFrom': args.rollback_from_sha or None, 'target': args.rollback_target_sha or None}
    receipt = {'contractVersion': CONTRACT_VERSION,
        'owner': {'project': args.owner_project, 'repo': args.owner_repo},
        'operation': {'fullSha': args.operation_sha}, 'workflowRun': int(args.workflow_run),
        'runtime': {'fullSha': args.runtime_sha}, 'rollback': rollback, 'phase': args.phase,
        'timestamp': utc_now(), 'overallStatus': status, 'urls': urls, 'edge': edge}
    expected = {'status': status, 'ownerProject': args.owner_project, 'ownerRepo': args.owner_repo,
        'operationSha': args.operation_sha, 'runtimeSha': args.runtime_sha,
        'workflowRun': int(args.workflow_run), 'phase': args.phase, 'rollback': rollback}
    verifier_module().verify(receipt, expected)
    payload = (json.dumps(receipt, sort_keys=True, separators=(',', ':')) + '\n').encode()
    fd = os.open(args.receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(payload)
        output.flush()
        os.fsync(output.fileno())
    print(f'shared edge contract v1 {status} for {args.phase}', file=sys.stderr if status != 'success' else sys.stdout)
    return 0 if status == 'success' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Exception as error:
        print(f'shared edge probe rejected: {type(error).__name__}:{error}', file=sys.stderr)
        raise SystemExit(1)
