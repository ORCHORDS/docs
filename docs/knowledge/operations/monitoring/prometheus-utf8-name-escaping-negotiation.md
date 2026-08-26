# Prometheus UTF-8 metric-name escaping negotiation

**Issue:** Producers and scrapers can disagree about non-legacy metric or label names, causing collisions, rejected scrapes, or queries that address a different series than intended.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Treat escaping as negotiated protocol behavior through the `escaping` parameter in Accept and Content-Type headers. Inventory producer and consumer support before selecting `allow-utf-8`, `underscores`, `dots`, or `values`. Prefer a reversible encoding when distinct source names could collapse under underscore replacement. Validate names before encoding, escape quoted exposition correctly, and keep dashboards and recording rules aligned with the ingested representation.

Build a collision report before migration and canary endpoints containing ASCII, dots, Unicode, underscores, quotes, and newlines. Do not allow user-controlled names to bypass cardinality limits or inject exposition syntax.

## Verification

Capture request and response negotiation headers and compare the exact stored names for every supported scheme. Test an unsupported scheme, omitted negotiation, invalid UTF-8, deliberate collisions, and mixed-version federation. Confirm alerts and remote write preserve the selected representation.

## Gotchas

- The default without negotiation is underscore escaping.
- Allowing UTF-8 requires both producer and consumer support.
- Renaming creates new series and may break historical continuity.

## Official source

- [Prometheus UTF-8 escaping schemes](https://prometheus.io/docs/instrumenting/escaping_schemes/)
