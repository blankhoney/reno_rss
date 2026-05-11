# Runbook: Backup & Restore

> Ref: [Audit Checklist](../superpowers/specs/2026-05-11-rss-audit-checklist.md) — OPS-01

## Backup

Run on the VPS (or trigger via cron):
```bash
cd /opt/myrss/app
bash infra/scripts/backup.sh
```

Backups are written to `./backup/<timestamp>/`:
```
backup/2026-05-11_23-00-00/
  miniflux.dump      # pg_dump -Fc compressed
  scoring.dump
  checksums.txt      # sha256sum of both dumps
```

**Schedule**: Recommended daily via cron:
```cron
0 2 * * * cd /opt/myrss/app && bash infra/scripts/backup.sh >> /var/log/myrss-backup.log 2>&1
```

**Retention**: Keep at minimum 7 daily backups. Delete older ones manually or via cron.

## Restore

> WARNING: Restore overwrites the target databases. Take a fresh backup first.

```bash
cd /opt/myrss/app
bash infra/scripts/restore.sh backup/<timestamp>
```

The script will:
1. Verify checksums before proceeding
2. Prompt for confirmation (`yes` required)
3. Stop `miniflux` and `scorer-worker` containers
4. Run `pg_restore --clean --if-exists` for both databases
5. Restart the stopped containers

## Verify restore

```bash
# Check Miniflux can read its DB
docker compose -p myrss-prod \
  -f infra/compose/docker-compose.base.yml \
  exec -T miniflux wget -qO- http://127.0.0.1:8080/readyz

# Check scoring DB row count
docker exec myrss-prod-postgres-1 \
  psql -U postgres -d scoring -c "SELECT COUNT(*) FROM item_scores;"
```

## pg_dump / pg_restore formats

- `-Fc` = custom format (compressed, supports selective restore)
- Restore with `pg_restore -Fc -d <db> --clean --if-exists`
- Use `-j 4` on restore for parallelism on large databases
