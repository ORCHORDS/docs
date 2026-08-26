# Prometheus scrape label-count limits

**Issue**

Unbounded labels per sample can exhaust memory and create expensive series.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set label count, name length, and value length limits per scrape job.
- Measure valid exporters before enforcement.
- Alert on limit failures rather than silently raising limits.

## Verification

1. Emit boundary and oversized samples.
2. Test relabeling before limits.
3. Measure memory under concurrent scrapes.

## Gotchas

- One bad sample can fail a scrape.
- Limits do not control series count alone.
- UTF-8 byte and character expectations differ.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
