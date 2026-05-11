# Runbook: Incident Response

> Ref: [Audit Checklist](../superpowers/specs/2026-05-11-rss-audit-checklist.md) — OPS-03

## Severity levels

| Level | Description | Response time |
|-------|-------------|--------------|
| P1    | Auth down / all users locked out | Immediate |
| P2    | Miniflux inaccessible / scoring stopped | < 1 hour |
| P3    | Scoring delayed / non-critical errors | < 24 hours |

---

## Diagnosis playbook

### Step 1: Check container status
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep myrss
```

### Step 2: Check Caddy logs
```bash
docker logs myrss-edge-caddy-1 --tail 50
```

### Step 3: Check Authelia logs
```bash
docker logs myrss-prod-authelia-1 --tail 50
```

### Step 4: Check Miniflux logs
```bash
docker logs myrss-prod-miniflux-1 --tail 50
```

### Step 5: Internal health check
```bash
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz
```

---

## Common incidents

### Authelia rate-limited (OTP fails)
```bash
# Restart Authelia to clear in-memory rate limits
docker restart myrss-prod-authelia-1

# Clear accumulated notification codes
docker exec myrss-prod-authelia-1 truncate -s 0 /config/notification.txt
```

### Caddy certificate error
Cause: DNS not pointing to VPS, or Let's Encrypt rate limit.
```bash
docker logs myrss-edge-caddy-1 | grep -i "error\|cert"
# Force cert renewal (if needed):
docker exec myrss-edge-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

### Miniflux DB connection failure
```bash
# Check postgres is running
docker ps | grep postgres
# Verify DATABASE_URL in compose env
docker inspect myrss-prod-miniflux-1 | grep -i DATABASE_URL
```

### Scorer worker not scoring
```bash
docker logs myrss-prod-scorer-worker-1 --tail 50
# Check API key validity
docker exec myrss-prod-scorer-worker-1 env | grep MINIFLUX_API_KEY
```

---

## Escalation

If rollback does not resolve a P1/P2:
1. Take a backup: `bash infra/scripts/backup.sh`
2. Restore last known-good backup: see [backup-restore.md](./backup-restore.md)
3. Rollback to last known-good tag: see [rollback.md](./rollback.md)

---

## Post-incident

- Document timeline in `docs/learning-notes.md`
- Add new error pattern to this runbook
- File a follow-up task if root cause needs a permanent fix
