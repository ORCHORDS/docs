# PostgreSQL 18 asynchronous-I/O rollout

**Issue:** Enabling a new I/O execution method without workload evidence can waste memory, exceed device queue capacity, or regress latency despite improving scan throughput.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

PostgreSQL 18 adds asynchronous I/O for eligible operations. Select `io_method` deliberately: `worker` uses I/O workers, `io_uring` requires a compatible build and kernel, and `sync` executes eligible operations synchronously. Establish a baseline before changing `io_workers`, `io_max_concurrency`, or combine limits. Respect that several settings require server restart and that `io_max_combine_limit` silently clamps `io_combine_limit`.

Tune against the actual storage stack, filesystem, virtualization layer, and concurrent connection load. Monitor `pg_aios`, scan and vacuum latency, device queueing, CPU, memory, and tail response times. Roll out by replica or host class and keep a tested path back to worker or sync mode.

## Verification

Benchmark sequential scans, bitmap heap scans, vacuum, and mixed OLTP under representative concurrency. Test cold and warm cache, throttled devices, io_uring unavailability, restart, failover, and parameter clamp behavior. Compare throughput and p95/p99 latency rather than accepting a single faster batch query.

## Gotchas

- PostgreSQL 17 lacks the PostgreSQL 18 AIO subsystem.
- Higher concurrency can increase device latency.
- Kernel and package builds determine io_uring availability.

## Official source

- [PostgreSQL resource configuration](https://www.postgresql.org/docs/current/runtime-config-resource.html#RUNTIME-CONFIG-RESOURCE-ASYNC-BEHAVIOR)
