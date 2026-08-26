# postgres-extensions-useful

**Issue:** Postgres ships with powerful extensions that go unused due to lack of awareness
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams build custom solutions for full-text search, UUID generation, or cryptography that Postgres handles natively via extensions.

## Pattern / Solution
Essential extensions: pg_stat_statements (query performance); pgcrypto (hashing, encryption); uuid-ossp or gen_random_uuid() (UUIDs); pg_trgm (trigram similarity search); hstore (key-value in column); ltree (hierarchical data); pg_repack (online table bloat removal); timescaledb (time-series); postgis (spatial).

## Gotchas
- Extensions must be installed on the server AND created per database
- Managed services limit available extensions -- check RDS/Cloud SQL extension allowlists
- shared_preload_libraries changes require Postgres restart

## Related
- full-text-search-tsvector
- postgis-spatial-data
- timescaledb-time-series
