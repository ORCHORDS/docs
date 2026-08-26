# Resource Timing next-hop protocol cohorts

**Issue:** Performance comparisons mix HTTP/1.1, HTTP/2, HTTP/3, cache, proxy, and unknown transports, hiding protocol-specific latency or regressions.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented with privacy/support caveats

`PerformanceResourceTiming.nextHopProtocol` reports the negotiated application-layer protocol for the connection as exposed by the user agent. Use controlled cohorts and preserve unknown values; it is not a complete network-path description.

**Source:** [W3C Resource Timing — nextHopProtocol](https://w3c.github.io/resource-timing/#dom-performanceresourcetiming-nexthopprotocol)

## Controls

- feature-detect and normalize through an allowlist;
- correlate with connection reuse, cache/service worker, timing visibility, route, and release;
- sample sanitized resource classes rather than full URLs;
- keep protocol choice in server/CDN configuration, not client analytics;
- avoid treating unknown as HTTP/1.1.

## Verification

Test H1/H2/H3, reused/new connections, proxy/CDN paths, service worker, cache, cross-origin with/without TAO, and unsupported engines. Compare field cohorts with server/CDN logs cautiously.

## Gotchas

The value describes the next hop visible to the client, not every upstream hop. Intermediaries can translate protocols. Protocol correlation does not establish causation.
