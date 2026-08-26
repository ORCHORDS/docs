# Resource Timing Timing-Allow-Origin redaction boundary

**Issue:** RUM interprets zero DNS, connection, request, and body-size fields as cache hits or instant network phases. For cross-origin resources, those values can instead be privacy redaction caused by a failed timing-allow check.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Classify each `PerformanceResourceTiming` entry by origin and Timing-Allow-Origin (TAO) visibility before deriving phase durations or compression/cache ratios. Treat zero/empty protected fields as unknown when the entry can be opaque. Preserve initiator, origin class, delivery type, status visibility, and browser version with the raw fields.

Configure TAO on controlled asset origins with the narrowest required origin set and test cached/revalidated responses. Keep CORS and TAO policies separate: allowing fetch access does not automatically expose timing, and timing exposure does not grant response-body access. Redact resource URLs before telemetry export.

## Verification

Test same-origin; cross-origin with no, matching, nonmatching, `null`, and wildcard TAO; redirects across origins; cached and revalidated responses; service-worker synthetic/forwarded responses; credentials; multiple header fields; and browsers that still mask selected size fields. Assert opaque samples never enter phase histograms as zero latency.

## Gotchas

A user agent may retain additional masking even when TAO is present. Service-worker client entries describe the client/worker interaction rather than every internal fetch, so a visible entry can still be incomplete network evidence.

## Sources

- W3C Web Performance WG, [Resource Timing: cross-origin resources and TAO](https://www.w3.org/TR/resource-timing/#sec-cross-origin-resources)
