# Prometheus label-name length budget

**Issue**

Very long label names inflate exposition, memory, remote-write payloads, and query ergonomics.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `label_name_length_limit` from conventions and backend compatibility.
- Reject generated schema keys as labels.
- Keep high-cardinality structured data in logs or traces.

## Verification

1. Test boundary lengths and UTF-8 names.
2. Verify remote-write consumers.
3. Scan exporter schema drift.

## Gotchas

- Length limits can fail whole scrapes.
- Renaming labels breaks queries.
- Name length and value length are separate.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
