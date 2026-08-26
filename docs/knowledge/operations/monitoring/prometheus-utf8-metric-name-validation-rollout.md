# Prometheus UTF-8 metric-name validation rollout

**Issue**

Changing metric-name validation can admit names that legacy integrations, queries, or remote systems cannot safely consume.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `metric_name_validation_scheme` explicitly per scrape job.
- Canary UTF-8 names through ingestion, rules, remote write, storage, dashboards, and exporters.
- Keep a reversible relabel policy for incompatible consumers.

## Verification

1. Scrape valid UTF-8, legacy-only, and invalid names.
2. Round-trip names through PromQL and APIs.
3. Verify alerts and recording rules after migration.

## Gotchas

- Validation and escaping schemes are separate settings.
- Downstream support may lag Prometheus.
- Relabeling can create collisions.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
