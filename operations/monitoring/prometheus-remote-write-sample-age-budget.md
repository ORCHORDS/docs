# Prometheus remote-write sample-age budget

**Issue**

An unlimited remote-write backlog can deliver operationally stale samples after an outage and consume WAL, network, and backend capacity long after their decision value expires.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `sample_age_limit` from the downstream freshness SLO, outage tolerance, and replay policy.
- Keep the limit greater than normal queue delay and monitor dropped-old samples separately from successful sends.
- Coordinate WAL retention, queue capacity, shard limits, and backend recovery throughput.
- Document which compliance or billing series must never use age-based dropping.

## Verification

1. Isolate the receiver, build a backlog across the limit, restore it, and verify old samples drop while fresh samples arrive.
2. Alert on highest sent timestamp lag, pending samples, retries, and age-limit drops.
3. Test clock skew and rolling reloads.

## Gotchas

- The default zero sends samples regardless of age.
- Dropping old samples creates intentional gaps and cannot be repaired from that sender later.
- A low limit can turn transient receiver latency into data loss.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#remote_write)
