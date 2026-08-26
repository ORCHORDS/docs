# Resource Timing response-status and content-type validation

**Issue:** Field telemetry reports that a resource was slow but cannot distinguish an HTTP error, an unexpected representation, or a valid response, leading teams to optimize latency while missing delivery failures.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented; newer Resource Timing fields require feature detection

Resource Timing exposes optional `responseStatus` and `contentType` attributes in newer implementations. Use them as sanitized diagnostic evidence alongside duration and sizes. They do not replace application validation, HTTP semantics, or server logs.

**Source:** [W3C Resource Timing specification](https://w3c.github.io/resource-timing/)

## Controls

- feature-detect each attribute and preserve an explicit unsupported/redacted bucket;
- group status by controlled classes or allowlisted codes rather than attaching full resource URLs;
- normalize content types case-insensitively and separate the media type from parameters;
- correlate status and type with `initiatorType`, transfer sizes, duration, and release;
- configure `Timing-Allow-Origin` only for origins intentionally permitted to expose detailed timing;
- cap and sample resource records so a large page cannot exhaust the telemetry budget.

## Verification

- fixtures cover successful responses, redirects, 204, 304/revalidation, 404, 5xx, CORS-redacted cross-origin resources, and service-worker responses;
- a stylesheet served as HTML and a script served with an unexpected media type appear in a mismatch cohort;
- unsupported browsers produce valid records without fabricated zeros;
- field samples reconcile with controlled browser traces and server/CDN logs without requiring exact one-to-one counts;
- query strings, fragments, credentials, tenant identifiers, and signed URLs never enter analytics.

## Gotchas

- a status of zero or an empty content type can reflect privacy restrictions or unavailable data, not a network failure.
- MIME sniffing, `nosniff`, and application acceptance rules are separate from the reported header value.
- cached, revalidated, and service-worker-delivered responses require cohorting before conclusions.
- `responseStatus` and `contentType` availability can vary by browser release; do not make product correctness depend on them.
