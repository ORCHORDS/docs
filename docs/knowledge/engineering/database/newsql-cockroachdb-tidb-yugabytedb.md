# NewSQL Databases — CockroachDB, TiDB, YugabyteDB

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your OLTP workload outgrows a single PostgreSQL instance. You need horizontal
scaling across regions with strong consistency, but NoSQL sacrifices the SQL
interface and ACID guarantees your application relies on.

## Context

NewSQL databases combine the relational model, SQL interface, and ACID
transactions of traditional RDBMS with the horizontal scalability and fault
tolerance of distributed NoSQL systems. The three leading open-source NewSQL
databases in 2026 are CockroachDB, TiDB, and YugabyteDB.

## Comparison

| Feature | CockroachDB | TiDB | YugabyteDB |
|---|---|---|---|
| Wire protocol | PostgreSQL | MySQL | PostgreSQL |
| Storage engine | Pebble (LSM) | TiKV (RocksDB) | DocDB (RocksDB) |
| Architecture | Monolithic binary | Disaggregated compute/storage | Disaggregated |
| Default isolation | Serializable | Snapshot (SI) | Snapshot |
| HTAP support | Limited | TiFlash columnar replicas | Limited |
| Geo-partitioning | Row-level locality | Placement rules | Tablespace-level |
| License | BSL 1.1 (→ Apache after 3yr) | Apache 2.0 | Apache 2.0 (core) |

## When to choose which

- **CockroachDB** — Postgres-compatible apps needing serializable isolation
  and multi-region active-active with automatic geo-partitioning. Strongest
  for financial workloads where serializability matters.
- **TiDB** — MySQL-compatible apps needing HTAP (real-time analytics on
  OLTP data via TiFlash). Wins on raw throughput when TiFlash is involved.
  Disaggregated compute/storage lets you scale SQL nodes independently.
- **YugabyteDB** — Postgres-compatible apps needing a fully open-source
  (Apache 2.0) distributed SQL with strong community. Good middle ground
  between CockroachDB's correctness focus and TiDB's throughput focus.

## Architecture patterns

### CockroachDB
Single binary handles SQL, distribution, and storage. Automatic range-based
sharding. Every node can serve reads and writes. Multi-region via locality-
aware replicas and zone configs.

### TiDB
Separates compute (TiDB servers for SQL parsing) from storage (TiKV for
transactional KV, TiFlash for columnar analytics). PD (Placement Driver)
handles scheduling and load balancing. Scale compute independently of
storage.

### YugabyteDB
Two-process model: YB-TServer (storage + tablet serving) and YB-Master
(catalog + coordination). Raft-based replication per tablet. Supports both
YSQL (Postgres) and YCQL (Cassandra-like) APIs.

## Anti-patterns

- **Treating NewSQL as a drop-in replacement** — query plans, locking
  behavior, and extension support differ from single-node Postgres/MySQL.
  Test your actual query patterns, not just schema compatibility.
- **Ignoring network latency** — cross-region transactions add latency
  proportional to round-trip time. Design for locality (partition data by
  region) or accept higher write latency.
- **Over-sharding small datasets** — NewSQL shines at scale. Under ~100 GB,
  a well-tuned single-node Postgres is simpler and faster.
- **Assuming identical SQL support** — each engine has gaps (e.g., stored
  procedures, triggers, specific extensions). Audit your SQL surface.

## Verification

- Run your application's integration test suite against the target NewSQL
  database with realistic data volume.
- Benchmark with your actual query mix using `EXPLAIN ANALYZE` equivalents.
- Test failover: kill a node mid-transaction and verify recovery.
- Measure cross-region write latency under production-like network conditions.

## Gotchas

- CockroachDB's BSL license restricts offering it as a managed service
  (converts to Apache 2.0 after 3 years). Check license compatibility.
- TiDB's MySQL compatibility is not 100% — some MySQL features (e.g., stored
  procedures, certain `GRANT` syntax) are unsupported or behave differently.
- YugabyteDB's YSQL layer adds overhead vs. native Postgres for simple
  point queries — expect ~2-5ms added latency on single-row reads.
- All three require careful clock synchronization (NTP/atomic clocks) for
  correct distributed transactions.
- Operational complexity is significantly higher than single-node Postgres.
  Budget for a dedicated team or managed service.

## Related

- `documentation/docs/policies/database/database-sharding-strategies.md`
- `documentation/docs/policies/database/distributed-transactions-saga.md`
- `documentation/docs/policies/database/transaction-isolation-levels.md`
- `documentation/docs/policies/database/postgres-high-availability-failover.md`

## Source URLs (verified 2026-08-16)

- CockroachDB vs TiDB vs YugabyteDB comparison — https://sanj.dev/post/distributed-sql-databases-comparison/
- TiDB vs YugabyteDB comparison guide — https://www.pingcap.com/compare/yugabytedb-vs-tidb/
- Best distributed SQL databases 2026 — https://www.pingcap.com/compare/best-distributed-sql-databases/
- NewSQL databases for streaming — https://www.conduktor.io/glossary/newsql-databases-streaming
- CockroachDB vs TiDB vs Spanner — https://www.designgurus.io/blog/cockroachdb-vs-tidb-vs-spanner
