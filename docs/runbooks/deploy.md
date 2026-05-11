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

## Miniflux API Key rotation (Task 3.5)

1. Login to Miniflux at `https://reader.<DOMAIN>`
2. Go to **Settings → API Keys → Create new key** (name: `scorer-worker`)
3. Update `.env` on server: `MINIFLUX_API_KEY=<new-key>`
4. Redeploy backend: `bash infra/scripts/deploy.sh prod <current-sha>`
5. Verify scorer-worker connects (check logs: `docker logs myrss-prod-scorer-worker-1`)
6. Delete old API key from Miniflux UI
