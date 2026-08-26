# connection-pool-sizing

**Issue:** Calculating the right connection pool size for your application
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Too few connections = request queuing; too many = PostgreSQL memory pressure and slow down.

## Pattern / Solution
```
# Rule of thumb (from HikariCP research)
pool_size = (number_of_cores * 2) + effective_spindle_count

# For a 4-core Postgres instance with SSD (spindle = 1):
pool_size = (4 * 2) + 1 = 9  →  round to 10

# For application side (Node.js, serverless):
# Each serverless worker needs its own pool → use connection pooler (PgBouncer)
# Lambda/Vercel: 1-2 connections per worker, many workers = overload without pooler

# PostgreSQL max_connections
SHOW max_connections;  -- default 100
# Formula: max_connections >= all_app_pools + admin_connections (3-5)
```

## Gotchas
- Serverless functions can spawn many instances simultaneously — always use a pooler
- Increasing max_connections increases shared_buffers memory per connection
- Monitor `pg_stat_activity` to see idle connections eating resources

## Related
- `connection-pooling-pgbouncer.md`
- `postgres-configuration-tuning.md`
