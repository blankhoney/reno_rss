#!/usr/bin/env python3
"""Idempotently restore only the fixed shared Caddy edge memberships."""
from __future__ import annotations

import json
import subprocess
import sys

CADDY = 'myrss-edge-caddy-1'
MYRSS = 'myrss-app'
BLOG_EDGE = 'brianstorm-edge'
BLOG_WEB = 'brianstorm-web'
STAGING_WEB = 'brianstorm-staging-web'


def die(message: str) -> 'None':
    print(f'shared-edge recovery: {message}', file=sys.stderr)
    raise SystemExit(1)


def docker(*args: str, capture: bool = True) -> str:
    try:
        result = subprocess.run(['docker', *args], check=True, text=True,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=15)
    except (OSError, subprocess.SubprocessError) as error:
        die(f'docker command failed: {type(error).__name__}')
    return result.stdout if capture else ''


def inspect_container(name: str) -> dict:
    try:
        value = json.loads(docker('inspect', name))
        if type(value) is not list or len(value) != 1:
            raise ValueError()
        networks = value[0].get('NetworkSettings', {}).get('Networks')
        if type(networks) is not dict:
            raise ValueError()
        return networks
    except (ValueError, json.JSONDecodeError):
        die(f'invalid container inspect: {name}')


def network_driver(name: str) -> str:
    try:
        value = json.loads(docker('network', 'inspect', name))
        if type(value) is not list or len(value) != 1 or type(value[0].get('Driver')) is not str:
            raise ValueError()
        return value[0]['Driver']
    except (ValueError, json.JSONDecodeError):
        die(f'invalid network inspect: {name}')


def ensure_membership(network: str) -> None:
    if network in inspect_container(CADDY):
        return
    try:
        docker('network', 'connect', network, CADDY, capture=False)
    except SystemExit:
        if network not in inspect_container(CADDY):
            die(f'cannot attach {CADDY} to {network}')
        return
    if network not in inspect_container(CADDY):
        die(f'{CADDY} is still detached from {network}')


def require_upstream(url: str, label: str) -> None:
    try:
        docker('exec', CADDY, '/bin/sh', '-ec', f'wget -q -T 5 -O /dev/null {url}', capture=False)
    except SystemExit:
        die(f'{label} upstream is unreachable')


def main() -> int:
    if len(sys.argv) != 1:
        die('this fixed contract accepts no arguments')
    if network_driver(MYRSS) != 'bridge' or network_driver(BLOG_EDGE) != 'bridge':
        die('required networks must use the bridge driver')
    if BLOG_EDGE not in inspect_container(BLOG_WEB):
        die('production Blog web is not attached to brianstorm-edge')
    try:
        staging = inspect_container(STAGING_WEB)
    except SystemExit:
        staging = None
    if staging is not None and BLOG_EDGE in staging:
        die('staging Blog web must never join production brianstorm-edge')
    ensure_membership(MYRSS)
    ensure_membership(BLOG_EDGE)
    require_upstream('http://web-prod:3000/', 'RSS')
    require_upstream('http://brianstorm-web:3000/api/status', 'Blog')
    print(f'shared-edge recovery passed: {CADDY} is attached to {MYRSS} and {BLOG_EDGE}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
