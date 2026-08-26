# network-waterfall-analysis

**Issue:** Request chains delay page load unnecessarily
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A waterfall diagram shows sequential vs. parallel requests. Chains where request A blocks B blocks C are common causes of high LCP and TTI. Each link adds at least one round-trip latency.

## Pattern / Solution
1. Identify chains: resources discovered only after parsing HTML then CSS then JS then fetch.\n2. Preload key resources to move them earlier in the waterfall.\n3. Inline critical CSS to eliminate one round trip for above-fold styles.\n4. Use HTTP/2 or HTTP/3 to parallelize requests on a single connection.\n5. Bundle or inline small resources to remove individual request overhead.

## Gotchas
- Preloading too many resources competes for bandwidth and can worsen LCP.\n- CDN caches often break HTTP/2 push (deprecated); rely on preload headers instead.\n- Third-party chains (analytics to tag manager to pixel) are often the deepest waterfalls.

## Related
chrome-devtools-network, resource-hints-preload, http2-multiplexing, critical-rendering-path
