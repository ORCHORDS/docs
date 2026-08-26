# postgresql-connection-pooling-pgbouncer

**Issue:** Reducing PostgreSQL connection overhead with PgBouncer connection pooling
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Each PostgreSQL connection consumes ~5–10 MB of memory and a backend process. Applications with many short-lived connections (serverless, microservices) exhaust `max_connections` or cause high connection establishment overhead.

## Pattern / Solution
Place PgBouncer between the application and PostgreSQL. Use transaction mode for most workloads.

**pgbouncer.ini:**
```ini
[databases]
mydb = host=127.0.0.1 port=5432 dbname=mydb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 5432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

# Pool mode
pool_mode = transaction       # transaction | session | statement

# Per-database pool size (connections to Postgres)
default_pool_size = 20
max_client_conn = 1000        # clients PgBouncer accepts
reserve_pool_size = 5         # extra connections for peak

# Timeouts
server_idle_timeout = 600     # close idle server connections
client_idle_timeout = 0       # 0 = never close idle clients
query_timeout = 0             # 0 = no per-query timeout

# Logging
log_connections = 0
log_disconnections = 0
log_pooler_errors = 1
```

**userlist.txt (scram-sha-256):**
```
# Generate hash: psql -c "SELECT concat('\"', usename, '\" \"', passwd, '\"') FROM pg_shadow WHERE usename='myuser';"
"myuser" "SCRAM-SHA-256$..."
```

**Postgres side — set max_connections conservatively:**
```sql
-- Max Postgres connections = PgBouncer's default_pool_size * num_databases + superuser reserve
ALTER SYSTEM SET max_connections = 100;
SELECT pg_reload_conf();
```

**Check pool stats:**
```bash
psql -h 127.0.0.1 -p 5432 -U pgbouncer pgbouncer -c "SHOW POOLS;"
psql -h 127.0.0.1 -p 5432 -U pgbouncer pgbouncer -c "SHOW STATS;"
```

## Gotchas
- `transaction` mode does not support prepared statements, `SET` session variables, or advisory locks that persist across transactions — use `session` mode for those.
- `LISTEN`/`NOTIFY` requires `session` mode; `transaction` mode drops the subscription between transactions.
- PgBouncer must be restarted (or `RELOAD` command issued) when adding new databases or changing `auth_file`.
- Serverless functions (Lambda, Cloud Run) that each open a connection still bypass the pool — use RDS Proxy or a persistent sidecar.

## Related
- `postgresql-vacuum-analyze.md`
- `postgresql-replication-lag.md`
- `postgresql-17-18-best-practices.md`
