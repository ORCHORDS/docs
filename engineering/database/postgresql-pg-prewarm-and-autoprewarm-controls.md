# PostgreSQL pg_prewarm and autoprewarm controls

**Issue:** Cold PostgreSQL caches after restart can cause severe latency spikes, but uncontrolled prewarming can displace useful pages and create startup I/O storms.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

The `pg_prewarm` extension can load relation blocks into the operating-system cache or PostgreSQL buffer cache. Its autoprewarm facility periodically records shared-buffer contents and reloads them after server restart when configured through shared preload libraries.

Use measured workload evidence to decide whether manual or automatic prewarming helps. Loading a large relation is not automatically beneficial: it consumes I/O and cache capacity and can evict pages needed by current traffic.

## Operational controls

- Enable the extension and any shared-preload configuration through the normal reviewed database-change process.
- Size and schedule warming against storage bandwidth, recovery objectives, and live query demand.
- Prefer the hottest relations or bounded block ranges over indiscriminate database-wide reads.
- Monitor buffer hits, physical reads, checkpoint/recovery state, and query latency.
- Confirm replicas and failover targets have an independent policy; do not assume primary cache state transfers.
- Keep application readiness separate from database process start when warm-up is required.

## Verification

1. Capture a cold-start baseline with representative queries.
2. Warm only selected relations and compare latency, physical reads, and cache residency.
3. Restart a non-production instance and verify autoprewarm dump and restore behavior.
4. Apply concurrent load and confirm warming does not starve foreground I/O.
5. Test operation without the extension so availability never depends solely on warmed cache.

## Sources

- [PostgreSQL 18: pg_prewarm](https://www.postgresql.org/docs/current/pgprewarm.html)
- [PostgreSQL 18: shared_preload_libraries](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-SHARED-PRELOAD-LIBRARIES)
