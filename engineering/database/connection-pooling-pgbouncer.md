# Database Connection Pooling

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application opens a new database connection for every request and
closes it when the request completes. Under load, PostgreSQL runs out of
connections (default max_connections = 100), returning "FATAL: too many
connections" errors. Each connection consumes 5-10 MB of memory on the
database server. Serverless functions and auto-scaling application
instances create unpredictable connection surges that overwhelm the
database.

## Context

Connection pooling places a pool manager between your application and
the database, maintaining a set of persistent connections that are shared
across application requests. Instead of creating a new TCP connection,
TLS handshake, and authentication for every query, requests borrow an
existing connection from the pool and return it when done. In 2026, the
standard PostgreSQL pooling stack includes PgBouncer (lightweight, C-based,
most deployed), Supavisor (Elixir-based, multi-tenant), and PgCat
(Rust-based, with sharding support). PostgreSQL 18 also introduces
built-in connection pooling capabilities.

## Why pooling matters

| Metric | Without pooling | With pooling |
|---|---|---|
| Connection setup time | 5-20ms per request | < 1ms (reuse) |
| Max concurrent queries | ~100 (PostgreSQL default) | Thousands of app connections → tens of DB connections |
| Memory per connection | 5-10 MB on DB server | Same, but fewer connections needed |
| Serverless compatibility | Every invocation = new connection | Pool absorbs connection churn |

## Pooling modes

### Session pooling

A database connection is assigned when the client connects and released
when the client disconnects. All PostgreSQL features work (prepared
statements, LISTEN/NOTIFY, session variables, temp tables).

**Use when:** application holds long-lived connections and needs full
PostgreSQL feature set.

### Transaction pooling

A database connection is assigned at the start of a transaction and
released at the end. Between transactions, the client has no database
connection. This allows many more clients than database connections.

**Use when:** application makes short, independent queries. This is the
default and recommended mode for most web applications.

**Limitations:** prepared statements (without named prepared statement
support), SET statements, LISTEN/NOTIFY, and advisory locks do not work
across transactions because the underlying connection changes.

### Statement pooling

A database connection is assigned for each individual SQL statement.
Most aggressive sharing, but multi-statement transactions are not
supported.

**Use when:** all queries are single-statement, auto-commit operations.

## Tool comparison

| Feature | PgBouncer | Supavisor | PgCat |
|---|---|---|---|
| Language | C | Elixir | Rust |
| Named prepared statements | Since v1.21 | Yes | Yes |
| Multi-tenancy | Manual config | Built-in per-tenant pools | Built-in |
| Sharding | No | No | Yes (read replicas, sharding) |
| Protocol | PostgreSQL wire | PostgreSQL wire | PostgreSQL wire |
| Connection limit | Thousands | Tens of thousands | Thousands |
| HA/clustering | External (HAProxy) | Built-in | Built-in |
| Monitoring | Stats via SHOW commands | Prometheus metrics | Prometheus metrics |

## PgBouncer configuration

```ini
# pgbouncer.ini
[databases]
mydb = host=db.example.com port=5432 dbname=mydb

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

; Pool sizing
pool_mode = transaction
default_pool_size = 20
min_pool_size = 5
max_client_conn = 1000
max_db_connections = 50

; Timeouts
server_idle_timeout = 300
client_idle_timeout = 0
query_timeout = 30
```

### Pool sizing guidelines

```
default_pool_size = number of CPU cores on DB server × 2-3
max_db_connections = max_connections on PostgreSQL minus reserved
min_pool_size = enough to handle baseline load without cold starts
max_client_conn = expected peak application connections
```

## Application-level pooling

Most ORMs and database drivers include built-in connection pools:

```typescript
// Node.js with pg pool
import { Pool } from 'pg';

const pool = new Pool({
  host: 'pgbouncer.example.com',
  port: 6432,
  max: 10,          // max connections in application pool
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});
```

When using an external pooler (PgBouncer), keep the application pool
size small (5-10) since the external pooler handles the actual connection
multiplexing.

## Anti-patterns

- **No pooling at all** — opening and closing connections per request in
  a web application. Even low-traffic apps benefit from a pool of 5-10
  connections.
- **Pool per microservice instance without limits** — 20 microservice
  replicas each with a pool of 20 connections = 400 connections to
  PostgreSQL. Coordinate pool sizes across services or use an external
  pooler.
- **Session pooling when transaction pooling suffices** — session pooling
  ties up connections for the lifetime of the client session, not just
  during active queries. Use transaction mode unless you need session-
  specific features.
- **Ignoring connection leak detection** — connections borrowed from the
  pool but never returned (due to error handling bugs) exhaust the pool.
  Configure leak detection timeouts.

## Gotchas

- **Prepared statement compatibility** — in transaction mode, traditional
  PgBouncer versions silently fail on prepared statements. PgBouncer
  1.21+ and Supavisor support named prepared statements in transaction
  mode. Verify your pooler version.
- **LISTEN/NOTIFY** — pub/sub notifications require a persistent
  connection. Use session mode for LISTEN/NOTIFY connections or a
  dedicated non-pooled connection.
- **Health checks** — poolers should perform health checks on backend
  connections before handing them to clients. A stale connection (from a
  PostgreSQL restart) causes the first query to fail.
- **SSL/TLS termination** — when placing a pooler between the app and
  database, SSL can terminate at the pooler. Ensure the pooler-to-
  database connection is also encrypted in production.

## Verification

- Application connects through a connection pooler, not directly to
  PostgreSQL.
- Pool mode is transaction (unless session-specific features are needed).
- Pool sizes are configured based on database server capacity.
- Connection leak detection is enabled with a timeout.
- Pooler metrics (active connections, waiting clients, query time) are
  monitored.
- No "too many connections" errors in production logs.

## Related

- `documentation/categories/database/postgresql-optimization.md`
- `documentation/categories/infra/docker-best-practices.md`
- `documentation/categories/performance/caching-strategies.md`

## Source URLs (verified 2026-08-16)

- PgBouncer setup guide — https://oneuptime.com/blog/post/2026-01-21-postgresql-pgbouncer-connection-pooling/view
- PostgreSQL connection pooling comparison — https://medium.com/@philmcc/postgresql-connection-pooling-pgbouncer-supavisor-built-in-a34d675db978
- Production Postgres pooling — https://nerdleveltech.com/production-postgres-pooling-pgbouncer-supabase-supavisor-tutorial
- PgBouncer scaling guide — https://planetscale.com/blog/scaling-postgres-connections-with-pgbouncer
