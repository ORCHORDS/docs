# Prometheus dropped-target retention budget

**Issue**

Keeping unlimited dropped service-discovery targets can consume memory and expose stale discovery metadata even though those targets are never scraped.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `keep_dropped_targets` per scrape job from a diagnostic need and memory budget; avoid the unlimited default where discovery churn is high.
- Relabel away sensitive metadata before a target can be retained for diagnostics.
- Monitor discovered, active, and dropped target counts plus Prometheus process memory.
- Use short-lived external discovery logs when deeper history is required instead of turning runtime state into an archive.

## Verification

1. Generate high-churn discovery input and confirm retained dropped targets stop at the configured bound.
2. Inspect the targets API/UI to ensure required diagnostic labels remain and sensitive labels do not.
3. Measure heap growth and reload behavior at the bound.

## Gotchas

- The limit is per scrape configuration, so totals add across jobs.
- A small bound reduces historical debugging context.
- Dropping a target does not automatically remove all labels from diagnostic state.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
