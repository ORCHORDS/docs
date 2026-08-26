# Prometheus scrape-failure log governance

**Issue**

A dedicated scrape-failure log improves diagnosis but can grow, leak target details, or become a hidden disk-pressure source.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `scrape_failure_log_file` only on controlled storage with rotation and retention.
- Restrict permissions and redact targets at ingestion where necessary.
- Monitor write failures, file size, and filesystem headroom.

## Verification

1. Trigger DNS, TLS, timeout, parse, and body-limit failures.
2. Rotate during active scrapes and verify reopening behavior.
3. Scan entries for credentials and sensitive query strings.

## Gotchas

- Empty configuration disables the log.
- Reload behavior must be tested with rotation.
- Failure logs complement metrics; they do not replace alerts.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
