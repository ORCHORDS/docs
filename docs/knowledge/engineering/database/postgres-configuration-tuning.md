# postgres-configuration-tuning

**Issue:** Default Postgres configuration is designed for minimal resource use, not production performance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Fresh Postgres install on a 32-core, 128GB RAM server still using shared_buffers = 128MB. Queries slower than expected.

## Pattern / Solution
Key GUCs: shared_buffers = 25% of RAM; effective_cache_size = 75% of RAM; work_mem = RAM / (max_connections * 2-4); maintenance_work_mem = 1-2GB; wal_buffers = 64MB; checkpoint_completion_target = 0.9; random_page_cost = 1.1 for SSD. Use pgtune.leopard.in for baseline.

## Gotchas
- work_mem is per-operation per-query -- high values with many parallel queries exhaust RAM
- shared_buffers changes require restart; work_mem changes take effect immediately
- Managed services expose a subset of GUCs via parameter groups

## Related
- autovacuum-tuning
- connection-limit-management
- vacuum-and-bloat-postgres
