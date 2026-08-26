# connection-pool-monitoring

**Issue:** Monitoring database connection pool saturation to prevent request queuing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Application latency spikes intermittently. Root cause is requests waiting for a free DB connection.

## Pattern / Solution
Expose pool metrics from your connection pooler (PgBouncer, HikariCP): pool_size, active_connections, idle_connections, waiting_clients. Alert when waiting_clients is greater than 0 sustained for 1min or active/pool_size exceeds 0.8. Use PgBouncer SHOW POOLS and SHOW STATS for detailed breakdown. Track connection acquisition time as a histogram.

## Gotchas
PgBouncer in transaction pooling mode multiplexes connections — effective pool size is much smaller than server max_connections. Connection pool exhaustion often means fixing query duration, not increasing pool size. SSL overhead on short queries is significant.

## Related
database-query-monitoring, slow-query-logging, queue-depth-monitoring
