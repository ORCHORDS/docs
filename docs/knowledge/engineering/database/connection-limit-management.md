# connection-limit-management

**Issue:** Too many client connections exhaust Postgres connection limit, causing connection errors
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
FATAL: sorry, too many clients already. Postgres default max_connections = 100. Each connection uses 5-10MB RAM. Kubernetes autoscaling creates connection spikes.

## Pattern / Solution
Deploy PgBouncer in front of Postgres. Set Postgres max_connections to 100-200 even for large instances. PgBouncer multiplexes thousands of app connections. Monitor with pg_stat_activity and pg_stat_database.numbackends.

## Gotchas
- Each Postgres connection forks a backend process -- 500 connections = 500 processes
- Application connection pools and PgBouncer pools stack; total connections = pool_size * app_instances
- PgBouncer transaction pooling breaks prepared statements

## Related
- connection-pooling-pgbouncer
- connection-pool-sizing
- postgres-configuration-tuning
