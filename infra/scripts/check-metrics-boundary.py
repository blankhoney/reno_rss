#!/usr/bin/env python3
"""Statically guard the public-deny/internal-scrape metrics contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = (ROOT / "infra/caddy/Caddyfile").read_text()
SMOKE_TEST = (ROOT / "infra/scripts/smoke-test.sh").read_text()


def site_block(host: str, stop_marker: str) -> str:
    try:
        tail = CADDYFILE.split(f"{host}.{{$DOMAIN}} {{", 1)[1]
        if stop_marker not in tail:
            raise IndexError
        return tail.split(stop_marker, 1)[0]
    except IndexError as exc:
        raise SystemExit(f"unable to locate Caddy site block for {host}") from exc


for host, stop_marker in (
    ("ai-reader", "staging-reader.{$DOMAIN} {"),
    ("staging-ai-reader", "import /etc/caddy/conf.d/*.caddy"),
):
    block = site_block(host, stop_marker)
    deny = "handle /api/metrics {\n        respond 404\n    }"
    general_api = "handle @api {"
    if block.count(deny) != 1:
        raise SystemExit(f"{host} must contain one exact /api/metrics 404 handler")
    if deny not in block or general_api not in block or block.index(deny) > block.index(general_api):
        raise SystemExit(f"{host} metrics denial must precede the general API proxy")

required_smoke_contract = (
    'require_http_status "/api/metrics" "404"',
    '-e INTERNAL_API_ALIAS="api-${ENV}"',
    '"$WORKER_CONTAINER" python -',
    '"ai_reader_up 1"',
    '"ai_reader_http_requests_total"',
    '"ai_reader_job_queue_queued"',
)
for marker in required_smoke_contract:
    if marker not in SMOKE_TEST:
        raise SystemExit(f"smoke test is missing metrics boundary marker: {marker}")

print("metrics boundary contract ok")
