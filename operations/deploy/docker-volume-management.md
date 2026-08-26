# docker-volume-management

**Issue:** Managing Docker volumes for data persistence, backup, and migration
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Anonymous volumes accumulate silently and fill disks. Named volumes lack backup automation. Bind mounts in production create permission and portability issues.

## Pattern / Solution
Named volume lifecycle:
```bash
# Create with labels
docker volume create \
  --label project=myapp \
  --label env=production \
  pgdata

# Inspect
docker volume inspect pgdata

# List with filter
docker volume ls --filter label=project=myapp

# Prune dangling volumes (anonymous only by default)
docker volume prune --filter label!=project=myapp

# Remove named volume (data is gone)
docker volume rm pgdata
```

Backup a volume:
```bash
# Run a temporary container to tar the volume contents
docker run --rm \
  -v pgdata:/data:ro \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/pgdata-$(date +%Y%m%d).tar.gz -C /data .

# Restore
docker run --rm \
  -v pgdata:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/pgdata-20260811.tar.gz -C /data
```

Volume driver for NFS shared storage:
```yaml
volumes:
  shared-assets:
    driver: local
    driver_opts:
      type: nfs
      o: addr=nfs-server.internal,rw,hard,nointr
      device: ":/exports/assets"
```

## Gotchas
- `docker compose down -v` removes named volumes defined in compose — never use in production without a backup
- Bind mounts (`./data:/var/lib/data`) have host-path dependency and break cross-host deployments
- Volume data is not deleted when a container is removed unless `--rm` or `down -v` is used
- Docker volume names are global per Docker daemon; two compose projects with the same volume name will conflict unless you set `COMPOSE_PROJECT_NAME`
- NFS volumes do not support file locking correctly for some databases (SQLite, PostgreSQL WAL)

## Related
- `docker-compose-production.md`
- `kubernetes-persistent-volumes.md`
- `disaster-recovery-failover.md`
