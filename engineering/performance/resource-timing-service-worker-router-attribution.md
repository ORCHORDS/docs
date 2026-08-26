# Resource Timing service-worker router attribution

**Issue:** Static service-worker routing sends some requests to cache, network, fetch handlers, or races, but telemetry attributes all of them to generic “service worker time.” Route regressions and unexpected fallbacks are then invisible.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** emerging specification fields; feature-detect

## Controls and implementation

Where supported, capture `workerRouterEvaluationStart`, `workerCacheLookupStart`, `workerMatchedRouterSource`, and `workerFinalRouterSource` with the ordinary resource timing entry. Store matched and final source separately: a matching rule describes routing intent, while a race or fallback can produce a different final source.

Cohort timings by service-worker version, route schema version, requested destination/method, matched source, and final source. Treat empty fields as unsupported or unavailable rather than as network routing. Bound URL cardinality and avoid exporting cache names or route data that reveal user state. Use these attributes for attribution, not to reconstruct authorization decisions.

## Verification

Test cache, network, fetch-event, and race sources; cache hit/miss; worker starting/already running; rule miss; updated worker; offline mode; navigation/subresource requests; opaque cross-origin entries; unsupported engines; and a race whose final source differs. Compare RUM attribution with controlled browser traces.

## Gotchas

The Service Worker static routing model and Resource Timing fields are evolving. A matched source is not proof that it supplied the response, timestamps may be unavailable, and client resource timing does not expose all internal worker fetch activity.

## Sources

- W3C Web Performance WG, [Resource Timing](https://www.w3.org/TR/resource-timing/)
- W3C Web Applications WG, [Service Workers Editor's Draft: static routing API](https://w3c.github.io/ServiceWorker/#service-worker-static-routing-api)
