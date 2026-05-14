# Runbook: Deploy

> Ref: [Audit Checklist](../superpowers/specs/2026-05-11-rss-audit-checklist.md) — CICD-03, CICD-04

## Prerequisites

- SSH access to VPS (`/opt/myrss/app`)
- `.env` populated on server with all required vars
- Secrets present at `/opt/myrss/secrets/`
- DNS A records pointing to VPS IP

## Staging deploy

Triggered automatically on push to `develop`.

Manual trigger:
```bash
ssh <user>@<vps-host>
cd /opt/myrss/app
git pull
bash infra/scripts/deploy.sh staging <git-sha>
```

## Production deploy

Triggered via **GitHub Actions → deploy-prod → Run workflow** (requires `production` environment approval).

Manual trigger (emergency only):
```bash
ssh <user>@<vps-host>
cd /opt/myrss/app
git pull
bash infra/scripts/deploy.sh prod <git-sha>
```

## Post-deploy health check

Verify readiness from inside the container network:
```bash
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz
```

Expected: `OK`

Also verify Authelia is healthy:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep myrss-prod
```
Expected: all containers show `Up ... (healthy)` or `Up ...`

For AI Reader scoring, verify reader-web can reach the internal scorer service:
```bash
docker exec myrss-prod-reader-web-1 node - <<'NODE'
const res = await fetch("http://scoring-service-prod:8000/healthz");
console.log(res.status);
console.log(await res.text());
NODE
```
Expected: HTTP `200` and `{"ok":true,...}`.

## Miniflux webhook for new-entry scoring

Miniflux webhooks are configured in Miniflux, not through the public Caddy
routes. Use the internal Docker alias:

- staging URL: `http://<SCORER_WEBHOOK_USERNAME>:<SCORER_WEBHOOK_PASSWORD>@scoring-service-staging:8000/webhooks/miniflux`
- prod URL: `http://<SCORER_WEBHOOK_USERNAME>:<SCORER_WEBHOOK_PASSWORD>@scoring-service-prod:8000/webhooks/miniflux`

Do not paste the real URL with password into chat or logs. After saving the
webhook in Miniflux, new entries should trigger `X-Miniflux-Event-Type:
new_entries` and scorer-worker will score up to the configured
`webhookMaxEntries`.

## VPS agent diagnostics

When local Codex cannot inspect VPS-only state, use
[vps-agent-diagnostics.md](./vps-agent-diagnostics.md) to collect a redacted,
read-only diagnosis from the VPS agent before changing deployment files or
restarting services.

## Miniflux credential rotation

scorer-worker and reader-web now use Miniflux Basic Auth via
`MINIFLUX_ADMIN` / `MINIFLUX_ADMIN_PASSWORD`.

1. Login to Miniflux at `https://reader.<DOMAIN>`.
2. Change the Miniflux user password.
3. Update `.env` on server: `MINIFLUX_ADMIN_PASSWORD=<new-password>`.
4. Redeploy backend: `bash infra/scripts/deploy.sh prod <current-sha>`
5. Verify scorer-worker connects (check logs: `docker logs myrss-prod-scorer-worker-1`)
