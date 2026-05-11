# Runbook: Rollback

> Ref: [Audit Checklist](../superpowers/specs/2026-05-11-rss-audit-checklist.md) — OPS-02

## When to rollback

- Health check fails after deploy
- Authelia restarting or rejecting logins
- Miniflux returns 5xx errors
- Critical scoring errors in logs

## Identify last known-good tag

```bash
cd /opt/myrss/app
git log --oneline -10
```

Note the commit SHA immediately before the failing deploy.

## Execute rollback

Via GitHub Actions (recommended):
- Go to **Actions → rollback → Run workflow**
- Set `env` = `prod` (or `staging`)
- Set `image_tag` = `<last-known-good-sha>`

Manual (emergency):
```bash
ssh <user>@<vps-host>
cd /opt/myrss/app
bash infra/scripts/rollback.sh prod <last-known-good-sha>
```

## Post-rollback verification

```bash
# Internal health check
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz

# Container status
docker ps --format "table {{.Names}}\t{{.Status}}" | grep myrss-prod
```

Expected: `OK` + all containers Up.

## Data safety note

`rollback.sh` only redeploys application containers — it does **not** touch the
`postgres_data` volume. Database state is preserved across rollbacks.
If schema migrations were applied during the bad deploy, you may need to restore
from backup: see [backup-restore.md](./backup-restore.md).
