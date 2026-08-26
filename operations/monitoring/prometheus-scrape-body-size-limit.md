# Prometheus scrape body-size limit

**Issue**

An unlimited metrics response lets a broken or hostile target consume network, memory, and parse time on every scrape.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `body_size_limit` from measured valid exposition size with headroom.
- Separate large legitimate exporters into governed jobs.
- Alert on limit failures and target growth before raising it.

## Verification

1. Serve responses below, at, and above the limit.
2. Test compressed and uncompressed exposition.
3. Measure scrape memory and duration under concurrency.

## Gotchas

- The limit is experimental/version-sensitive.
- Rejected scrapes create gaps.
- Compression ratios can hide large decoded payloads.

## Official source

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config)
