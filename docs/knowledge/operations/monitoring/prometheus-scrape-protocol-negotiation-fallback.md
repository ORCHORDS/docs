# Prometheus scrape-protocol negotiation and fallback

**Issue:** Metrics targets with missing or invalid Content-Type headers can begin failing after a Prometheus v3 migration, while an indiscriminate fallback may parse bytes under the wrong exposition format.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Require targets to return a valid Content-Type matching their selected protocol. Configure `scrape_protocols` in an intentional preference order and add `fallback_scrape_protocol` only for a known legacy target whose emitted format has been verified. Scope fallback per job rather than globally whenever possible, and track it as migration debt with an owner and removal date.

Capture response headers and a sanitized fixture before choosing a fallback. Protobuf, OpenMetrics, and Prometheus text versions are not interchangeable labels. Revalidate negotiation after enabling native histograms or UTF-8 behavior because accepted protocol ordering can change.

## Verification

Exercise every target with its normal Accept header, then test blank, malformed, unsupported, and contradictory Content-Type values. Verify expected scrape success or failure, sample counts, HELP/TYPE handling, UTF-8 names, and that fallback cannot accept an unrelated payload. Alert on scrape failures and remaining fallback use.

## Gotchas

- Prometheus v3 is intentionally stricter than v2.
- Fallback hides producer defects if left permanent.
- Parsing the wrong format can be worse than a failed scrape.

## Official source

- [Prometheus scrape protocol content negotiation](https://prometheus.io/docs/instrumenting/content_negotiation/)
- [Prometheus v3 migration guidance](https://prometheus.io/docs/prometheus/latest/migration/#scrape-protocols)
