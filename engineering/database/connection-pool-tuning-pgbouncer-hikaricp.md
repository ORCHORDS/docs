# Connection Pool Tuning — PgBouncer, HikariCP, and Pool Sizing

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application intermittently throws "connection pool exhausted"
errors under moderate load. Database CPU is at 10% but the application
cannot get connections. You set `maxPoolSize=200` thinking more
connections would help, but PostgreSQL now shows 3,000 connections
across 15 application instances, thrashing on context switches.
Meanwhile, a single slow query holds a connection for 30 seconds,
starving all other requests in that instance's pool.

## Context

Database connection pooling reuses a fixed set of database connections
across application requests, avoiding the overhead of establishing a
new connection per query (TCP handshake, TLS negotiation,
authentication — typically 20-50ms per connection). In 2026, the
standard production pattern combines an application-level pool
(HikariCP for JVM, Drizzle/node-postgres for Node.js, SQLAlchemy for
Python) with an external pooler (PgBouncer, PgCat, Supabase Vibes)
in front of PostgreSQL. The application pool prevents individual
instances from thrashing; the external pool caps the total connections
the database ever sees across all instances. The HikariCP pool sizing
formula — `(core_count * 2) + effective_spindle_count` — typically
produces pools of 10-30 connections, not hundreds.

## Pool sizing formula

```
HikariCP formula:
  pool_size = (CPU cores * 2) + effective_spindle_count

  4-core server with SSD: (4 * 2) + 1 = 9-10 connections
  8-core server with SSD: (8 * 2) + 1 = 17 connections

Why small pools work:
  → PostgreSQL handles concurrent queries via internal multiplexing
  → More connections = more context switching = slower overall
  → A pool of 10 saturates a 4-core database server
  → 50 app instances × 10 connections = 500 total (still manageable)

PostgreSQL max_connections:
  → Default: 100 (often too low for production)
  → Recommended: set based on available memory
  → Each connection uses ~5-10 MB of memory
  → 200 connections × 10 MB = 2 GB just for connections
  → With PgBouncer: database needs far fewer actual connections
```

## PgBouncer configuration

```ini
; /etc/pgbouncer/pgbouncer.ini

[databases]
myapp = host=localhost port=5432 dbname=myapp

[pgbouncer]
; Pool mode: transaction (recommended), session, statement
pool_mode = transaction

; Max connections PgBouncer opens to PostgreSQL
default_pool_size = 20

; Extra connections for burst traffic
reserve_pool_size = 5
reserve_pool_timeout = 3

; Max client connections PgBouncer accepts
max_client_conn = 1000

; Connection limits per user/database
max_db_connections = 50
max_user_connections = 50

; Timeouts
server_idle_timeout = 300
client_idle_timeout = 0
query_timeout = 30
query_wait_timeout = 30

; Logging
log_connections = 0
log_disconnections = 0
log_pooler_errors = 1

; Authentication
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
```

```
Pool modes:
  session:      connection locked to client for entire session
                (most compatible, least efficient)
  transaction:  connection returned after each transaction
                (recommended for most apps)
  statement:    connection returned after each statement
                (only for simple queries, no multi-statement txns)

Architecture:
  App instances → PgBouncer → PostgreSQL
  1000 clients → 20 server connections → database
  98% reduction in database connection count
```

## HikariCP configuration

```yaml
# application.yml (Spring Boot)
spring:
  datasource:
    hikari:
      maximum-pool-size: 10
      minimum-idle: 10          # Keep pool full (best perf)
      connection-timeout: 5000  # Fail fast (5 seconds)
      idle-timeout: 600000      # 10 minutes
      max-lifetime: 1800000     # 30 minutes (< DB timeout)
      leak-detection-threshold: 30000  # Log leak after 30s
      validation-timeout: 3000
      pool-name: MyApp-Pool

      # Connection test query (for older JDBC drivers)
      # connection-test-query: SELECT 1

      # Metrics (Micrometer/Prometheus)
      register-mbeans: true
```

```java
// Programmatic configuration
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:postgresql://pgbouncer:6432/myapp");
config.setMaximumPoolSize(10);
config.setMinimumIdle(10);
config.setConnectionTimeout(5000);
config.setLeakDetectionThreshold(30000);
config.setMetricRegistry(prometheusRegistry);

HikariDataSource ds = new HikariDataSource(config);
```

## Node.js pool configuration

```javascript
// node-postgres (pg) pool
const { Pool } = require('pg');

const pool = new Pool({
  host: 'pgbouncer-host',
  port: 6432,
  database: 'myapp',
  max: 10,                    // Max connections in pool
  idleTimeoutMillis: 30000,   // Close idle connections after 30s
  connectionTimeoutMillis: 5000, // Fail if no connection in 5s
  allowExitOnIdle: true,      // Allow process exit when idle
});

pool.on('error', (err) => {
  console.error('Unexpected pool error', err);
});

pool.on('connect', (client) => {
  // Set session-level config if needed
  client.query("SET statement_timeout = '30s'");
});

// Always release connections
async function queryWithRelease(sql, params) {
  const client = await pool.connect();
  try {
    return await client.query(sql, params);
  } finally {
    client.release();
  }
}
```

## Monitoring and diagnostics

```sql
-- PostgreSQL: active connections by state
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname = 'myapp'
GROUP BY state;

-- Connections by application
SELECT application_name, count(*)
FROM pg_stat_activity
WHERE datname = 'myapp'
GROUP BY application_name;

-- Long-running queries (connection hogs)
SELECT pid, now() - pg_stat_activity.query_start AS duration,
       query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '30 seconds'
  AND state != 'idle';
```

```
-- PgBouncer admin console
SHOW POOLS;    -- pool sizes and usage
SHOW STATS;    -- request/query counts, timing
SHOW CLIENTS;  -- connected clients
SHOW SERVERS;  -- backend connections
SHOW LISTS;    -- internal queue lengths

Key metrics to monitor:
  → Pool wait time (time waiting for available connection)
  → Active connections vs pool size
  → Connection creation rate
  → Leak detection warnings
  → Query timeout rate
```

## Anti-patterns

- **Oversized pools** — setting `maxPoolSize=200` per instance.
  With 20 instances, that is 4,000 potential connections to the
  database. PostgreSQL performance degrades sharply above a few
  hundred connections due to context switching. Use small pools
  (10-30) per instance with PgBouncer to multiplex.
- **Not releasing connections** — forgetting to close or release
  connections in error paths. Use try/finally, connection managers,
  or ORM-managed connections to guarantee release.
- **Session pool mode with connection pooling** — using PgBouncer
  in session mode defeats the purpose of pooling. Use transaction
  mode for most applications. Only use session mode if your app
  uses session-level features (prepared statements, advisory locks).
- **No leak detection** — running without leak detection means
  leaked connections silently exhaust the pool under load. Enable
  HikariCP's `leakDetectionThreshold` or equivalent monitoring.

## Gotchas

- **PgBouncer transaction mode and prepared statements** — in
  transaction mode, PgBouncer reassigns server connections between
  transactions. Named prepared statements created in one
  transaction may not exist in the next. Use
  `server_reset_query = DISCARD ALL` or avoid named prepared
  statements.
- **Connection max-lifetime vs database timeout** — if the pool's
  `maxLifetime` exceeds PostgreSQL's `idle_in_transaction_session_timeout`
  or a firewall's TCP timeout, connections will be silently dropped.
  Set `maxLifetime` shorter than the shortest timeout in the path.
- **Health check overhead** — frequent connection validation
  queries (`SELECT 1`) add overhead. Modern JDBC drivers support
  `Connection.isValid()` which uses a lightweight protocol-level
  ping instead of a SQL query.
- **Serverless and connection storms** — serverless functions
  (Lambda, Workers) create new connections on every cold start.
  Use external poolers (PgBouncer, RDS Proxy, Supabase connection
  pooler) to absorb connection storms from serverless.

## Verification

- Pool size follows the `(cores * 2) + spindles` formula.
- PgBouncer runs in transaction mode between app and database.
- Total connections across all instances stay within database limits.
- Leak detection is enabled with appropriate thresholds.
- Pool metrics are exported to monitoring (Prometheus/Datadog).
- Connection timeouts fail fast (5-10 seconds, not 30+).

## Related

- `documentation/categories/database/postgresql-query-optimization.md`
- `documentation/categories/database/zero-downtime-schema-migrations.md`
- `documentation/categories/infra/observability-stack-metrics-logs-traces.md`

## Source URLs (verified 2026-08-16)

- Database Connection Pooling Best Practices 2026 — https://dohost.us/index.php/2026/07/28/the-complete-handbook-of-database-connection-pooling-best-practices/
- Database Connection Pool Tuning: HikariCP, PostgreSQL — https://codesprintpro.com/blog/database-connection-pool-tuning/
- PostgreSQL Connection Pooling 2026: PgBouncer vs Built-In — https://postgresqlhtx.com/postgresql-connection-pooling-in-2026-when-to-use-pgbouncer-vs-built-in-pooling/
- Connection Pooling: PgBouncer, HikariCP — https://viprasol.com/blog/database-connection-pooling/
