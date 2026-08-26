# intersection-observer-performance

**Issue:** Scroll event listeners for visibility detection block the main thread
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Scroll listeners fire dozens of times per second and force layout queries. IntersectionObserver runs asynchronously off the main thread and fires only when visibility changes.

## Pattern / Solution
1. Create observer with IntersectionObserver callback and options including rootMargin.\n2. Use rootMargin to load content slightly before it enters the viewport.\n3. Use threshold for percentage-based visibility triggers.\n4. Disconnect observer when done: observer.disconnect().

## Gotchas
- IntersectionObserver does not report exact pixel positions; for precise positioning, fall back to scroll listeners.\n- Entries with isIntersecting: false fire on initial observation if element is offscreen; handle this case.\n- Not available in IE11; use a polyfill or feature-detect.

## Related
image-lazy-loading, below-fold-defer, resize-observer-performance
