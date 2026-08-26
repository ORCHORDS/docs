# Prometheus out-of-order ingestion window budget

**Issue**

Allowing out-of-order samples can absorb delayed delivery, but expands mutable head state and can hide clock or buffering faults.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `out_of_order_time_window` from a measured lateness distribution and query correctness need.
- Keep clocks monitored and reject series whose lateness exceeds policy.
- Canary memory and compaction impact before widening the window.
- Separate legitimate delayed pipelines from ordinary scrapes.

## Verification

1. Replay samples at boundaries inside and outside the window.
2. Measure head memory, WAL, compaction, and query results.
3. Test restart and remote-write forwarding.

## Gotchas

- A wider window is not a fix for clock skew.
- Late samples can revise recent query results.
- Zero disables out-of-order ingestion.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#storage_config)
