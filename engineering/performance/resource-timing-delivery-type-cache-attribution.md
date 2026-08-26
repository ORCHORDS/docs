# Resource Timing deliveryType cache attribution

**Issue:** A fast resource may have arrived from a local cache, a service worker, or the network. Grouping all short durations as cache hits produces misleading performance conclusions.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — deliveryType availability varies; retain fallback attribution

## Decision

Use `PerformanceResourceTiming.deliveryType` as optional evidence in resource-level telemetry, combined with transfer sizes and service-worker timing. Treat unknown or unsupported values explicitly.

## Controls

- Feature-detect `deliveryType` and allowlist documented values.
- Preserve an `unknown` bucket instead of guessing.
- Correlate with `transferSize`, `encodedBodySize`, `decodedBodySize`, and `workerStart`.
- Respect Timing-Allow-Origin; do not bypass cross-origin redaction.
- Strip query strings and sensitive URL components before telemetry.
- Sample and cap resource records per page.
- Separate reload, cold navigation, warm navigation, and service-worker-controlled cohorts.
- Version browser and release dimensions.

## Verification

Test memory cache, disk cache where observable, revalidation, service-worker cache, network fetch, cross-origin resources with and without Timing-Allow-Origin, disabled cache, and unsupported browsers. Compare field attribution with controlled DevTools traces without requiring exact one-to-one internal-cache visibility.

## Gotchas

Browser cache internals and eviction are implementation details. Zero transfer size is not sufficient by itself to identify a cache source. Privacy restrictions can hide fields; absence is not a network diagnosis.

## Sources

- [W3C Resource Timing: deliveryType](https://w3c.github.io/resource-timing/#dom-performanceresourcetiming-deliverytype)
- [W3C Resource Timing](https://www.w3.org/TR/resource-timing/)
- [MDN PerformanceResourceTiming](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming)
