# Prometheus explicit-timestamp staleness policy

**Issue**

Targets that attach their own timestamps have different stale-marker behavior and can leave misleading series when scrape delivery stops.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `track_timestamps_staleness` explicitly for jobs using supplied timestamps.
- Keep exporter clocks monitored and label the ownership of timestamp semantics.
- Test alert expressions across target loss and recovery.

## Verification

1. Stop the exporter and inspect stale markers and query results.
2. Inject clock skew and repeated timestamps.
3. Compare jobs with Prometheus-assigned timestamps.

## Gotchas

- Explicit timestamps can conceal scrape time.
- Staleness policy changes query continuity.
- Clock correction can create out-of-order samples.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
