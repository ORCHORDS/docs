# SQLite in Production — WAL Mode, Litestream Replication, and Edge Computing

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your team defaults to PostgreSQL for every project, including an
internal dashboard with 50 users and a read-heavy API serving cached
data. The PostgreSQL instance costs $200/month, requires connection
pooling configuration, and needs a DBA to manage backups and
failover. Meanwhile, your edge-deployed Workers cannot connect to
a centralized database without 30-80ms latency per query, negating
the edge deployment advantage.

## Context

SQLite in production has matured significantly by 2026. WAL (Write-
Ahead Logging) mode enables concurrent readers alongside a single
writer, achieving 100,000+ read QPS on NVMe storage. Litestream
provides continuous streaming replication to S3/GCS/Azure Blob with
seconds-level RPO. Distributed SQLite solutions — Cloudflare D1,
Turso/libSQL, and LiteFS — bring SQLite to the edge with sub-10ms
read latency. The 2026 consensus: default to SQLite until you have
a concrete reason for PostgreSQL (multi-writer, horizontal scaling,
row-level security, or complex multi-tenant isolation).

## WAL mode configuration

```sql
-- Enable WAL mode (persistent — survives restarts)
PRAGMA journal_mode=WAL;

-- NORMAL sync is safe with WAL (fsync on checkpoint, not every write)
PRAGMA synchronous=NORMAL;

-- Wait up to 5 seconds for write lock instead of failing immediately
PRAGMA busy_timeout=5000;

-- Memory-mapped I/O for faster reads (256MB)
PRAGMA mmap_size=268435456;

-- Cache size (negative = KB, positive = pages)
PRAGMA cache_size=-64000;
```

```
WAL mode vs rollback journal:

  Aspect              WAL Mode            Rollback Journal
  ──────────────────────────────────────────────────────────
  Concurrent reads    Yes (while writing)  Blocked during write
  Write performance   Faster (append)      Slower (copy-on-write)
  Read performance    100K+ QPS on NVMe    Lower throughput
  Checkpoint          Periodic WAL→DB      N/A
  File count          3 (.db, -wal, -shm)  2 (.db, -journal)

  WAL appends changes to a separate -wal file.
  Readers see a consistent snapshot without blocking.
  Checkpointing merges WAL back into the main database.
```

## Litestream (streaming replication to S3)

```yaml
# litestream.yml
access-key-id: AKIAxxxxxxxxxxxxxxxx
secret-access-key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
dbs:
  - path: /data/app.db
    replicas:
      - url: s3://mybucket/app.db
    sync-interval: 1s
```

```bash
# Start replication (runs as sidecar process)
litestream replicate /data/app.db s3://mybucket/app.db

# Restore from backup (refuses if output file exists)
litestream restore -o /data/app.db s3://mybucket/app.db

# Restore to a specific point in time
litestream restore -o /data/app.db -timestamp 2026-08-16T10:00:00Z \
  s3://mybucket/app.db
```

```
Litestream architecture:

  App → writes → SQLite (WAL mode)
                    ↓
  Litestream sidecar monitors WAL changes
                    ↓
  Streams WAL frames continuously to S3/GCS/Azure
                    ↓
  RPO: seconds (not hours like periodic snapshots)
  Point-in-time recovery from any WAL position

  Key: Litestream is a replication tool, not a distributed
  database. One writer, continuous backup, fast restore.
```

## Distributed SQLite (edge patterns)

```
Three approaches (all mature by 2026):

  Solution        How it works                  Best for
  ──────────────────────────────────────────────────────────
  Cloudflare D1   SQLite in Workers runtime,    Cloudflare-native
                  managed replication            apps, Workers

  Turso/libSQL    SQLite fork with server mode,  Multi-region reads,
                  HTTP replication, embedded     any platform
                  replicas (local sync)

  LiteFS          FUSE filesystem intercepts     Fly.io deployments,
  (Fly.io)        WAL, ships pages to replicas   transparent replication

  Edge read latency:
    Centralized DB: 30-80ms
    Edge replica:   <10ms (often microseconds for local reads)
```

## SQLite vs PostgreSQL decision

```
Default to SQLite when:
  → Single-writer, read-heavy (90%+ reads)
  → Fits on one machine (< 1TB typical)
  → Internal tools, dashboards, MVPs, early-stage SaaS
  → Edge deployment with local data
  → Simpler ops (no connection pooling, no DBA)

Require PostgreSQL when:
  → Concurrent multi-writer access needed
  → Multi-region failover / horizontal scaling
  → Complex queries (CTEs, window functions at scale)
  → Row-level security for multi-tenant isolation
  → Need extensions (PostGIS, pgvector, pg_cron)
  → Compliance requires managed DB with audit logging
```

## Anti-patterns

- **Using rollback journal mode in production** — WAL mode provides
  dramatically better concurrent read performance. Always enable
  WAL mode for production workloads.
- **Running periodic backup snapshots instead of Litestream** —
  hourly snapshots mean up to an hour of data loss on failure.
  Litestream streams continuously with seconds-level RPO.
- **Defaulting to PostgreSQL for every project** — a dashboard
  with 50 users does not need a managed database. SQLite eliminates
  connection pooling, backup configuration, and DBA overhead.
- **Multiple writer processes on the same SQLite file** — SQLite
  supports only one writer at a time. Use busy_timeout for short
  contention or move to PostgreSQL for true concurrent writes.

## Gotchas

- **WAL file growth** — without periodic checkpointing, the WAL
  file can grow indefinitely. SQLite auto-checkpoints at 1000
  pages by default (`PRAGMA wal_autocheckpoint`). Monitor WAL
  file size in production.
- **Network filesystems** — SQLite relies on filesystem locking.
  NFS, SMB, and most network filesystems do not provide reliable
  locking. Run SQLite on local storage only.
- **Litestream restore safety** — `litestream restore` refuses to
  run if the output file already exists, preventing accidental
  overwrite. Delete or move the existing file before restoring.
- **LiteFS maturity** — still pre-1.0 with no guaranteed roadmap.
  For new projects, Turso or D1 are considered safer long-term
  bets for distributed SQLite.
- **PRAGMA persistence** — `journal_mode=WAL` is persistent across
  connections, but `synchronous`, `busy_timeout`, and `cache_size`
  must be set on each connection open.

## Verification

- WAL mode enabled with `PRAGMA journal_mode=WAL`.
- `synchronous=NORMAL` set for WAL mode safety.
- `busy_timeout` configured to handle write contention.
- Litestream replication running as sidecar with continuous sync.
- Restore procedure tested and documented.
- WAL file size monitored with appropriate checkpoint settings.

## Related

- `documentation/categories/database/postgresql-jsonb-indexing-querying.md`
- `documentation/categories/cloudflare/d1-sqlite-edge-database.md`
- `documentation/categories/database/connection-pool-tuning-pgbouncer-hikaricp.md`

## Source URLs (verified 2026-08-16)

- SQLite in 2026: Why Serious Apps Are Choosing It Over Postgres — https://www.javacodegeeks.com/2026/05/sqlite-in-2026-why-serious-apps-are-choosing-it-over-postgres.html
- SQLite for Production: Beyond Prototyping — https://daily.dev/blog/sqlite-production-guide-when-how-to-use-beyond-prototyping/
- Litestream Configuration Reference — https://litestream.io/reference/config/
- Distributed SQLite: LibSQL and Turso — https://dev.to/dataformathub/distributed-sqlite-why-libsql-and-turso-are-the-new-standard-in-2026-58fk
