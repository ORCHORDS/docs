# chrome-devtools-network

**Issue:** Network requests are slow or ordered suboptimally
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Chrome DevTools Network panel shows every request, timing breakdown (DNS, connect, TTFB, download), priority, and protocol.

## Pattern / Solution
1. Filter by type (JS, CSS, Img, XHR) to focus on specific resource categories.\n2. Check Initiator column to see what triggered each request.\n3. Sort by Waterfall to visualize request chaining.\n4. Enable Big request rows and Show overview for full timing context.\n5. Check response headers for Cache-Control, Content-Encoding, and protocol version.

## Gotchas
- DevTools throttling adds fixed latency; it doesn't emulate real mobile network variability.\n- Disk cache vs. Memory cache hits look different; disk cache still involves some overhead.\n- Service Worker intercepts show as (ServiceWorker) in the Initiator column.

## Related
network-waterfall-analysis, cache-control-headers, service-worker-cache-strategy, http2-multiplexing
