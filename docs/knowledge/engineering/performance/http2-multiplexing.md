# http2-multiplexing

**Issue:** HTTP/1.1 connection limits throttle parallel resource loading
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
HTTP/1.1 browsers open 6 connections per origin; resources beyond that queue. HTTP/2 multiplexes unlimited streams over a single connection, eliminating this bottleneck.

## Pattern / Solution
1. Enable HTTP/2 on your server (nginx: listen 443 ssl http2;).\n2. Consolidate resources to a single origin to maximize multiplexing benefit.\n3. Eliminate HTTP/1.1 workarounds: domain sharding, sprite sheets, CSS concatenation.\n4. Serve small resources individually (HTTP/2 handles the overhead).\n5. Verify with Chrome DevTools Network > Protocol column shows h2.

## Gotchas
- HTTP/2 requires TLS; no plaintext HTTP/2 in browsers.\n- HTTP/2 server push is deprecated; use preload headers instead.\n- A single slow response can still cause head-of-line blocking at TCP layer -- HTTP/3 fixes this.

## Related
http3-quic-benefits, network-waterfall-analysis, cdn-cache-strategy
