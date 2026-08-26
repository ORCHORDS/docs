# Service Worker Navigation Preload Race Control

**Issue:** A cold service worker serializes startup before its navigation fetch, adding latency; naive preload integration can issue a second network request or cache incompatible variants.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Feature-detect `registration.navigationPreload` and enable it during the service worker's activate event with `event.waitUntil()`. For navigation requests, check an acceptable cache entry first, then await `event.preloadResponse`, and call `fetch()` only when neither produced a response. Cache a clone only under the same rules used for ordinary network responses.

If the origin customizes preload responses using `Service-Worker-Navigation-Preload`, return a complete contract understood by the worker and set `Vary: Service-Worker-Navigation-Preload` so shared caches do not mix variants. Keep an offline fallback independent of preload success.

## Verification

Measure cold-worker navigations, warm-worker navigations, offline mode, slow origin, preload rejection, cache hit, redirect, authenticated page, and unsupported browsers. In a network trace, confirm exactly one origin request on the preload path and no body-consumption error. Validate variant cache keys and response headers through the CDN.

## Gotchas

Navigation preload covers navigations, not every subresource. Ignoring `preloadResponse` wastes the parallel request. Awaiting it indefinitely without a fallback can transfer latency elsewhere. Personalized responses need ordinary cache and privacy controls; the preload header does not make caching safe.

## Sources

- [W3C Service Workers specification](https://www.w3.org/TR/service-workers/)
- [MDN NavigationPreloadManager](https://developer.mozilla.org/en-US/docs/Web/API/NavigationPreloadManager)
