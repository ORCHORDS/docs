# WebSocket permessage-deflate Resource Bounds

**Issue:** WebSocket compression saves bandwidth but increases CPU and per-connection memory; default context takeover can amplify resource pressure across thousands of mostly idle connections.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Negotiate `permessage-deflate` explicitly and benchmark it against real message distributions. Use the RFC 7692 no-context-takeover and maximum-window-bits parameters to bound compressor/decompressor memory where the stack supports them. Skip compression for small or already compressed payloads and impose decompressed message, ratio, CPU-time, and concurrent-work limits.

Expose metrics for negotiated parameters, wire and decompressed bytes, compression ratio, CPU, memory per connection, event-loop delay, and rejected messages. Apply backpressure before compression queues grow, and shed optional compression rather than jeopardizing connection health.

## Verification

Test negotiation accepted/declined, each context-takeover direction, window sizes, fragmented messages, empty and incompressible payloads, high-ratio adversarial input, slow consumers, reconnect storms, and mixed client libraries. Load-test at target concurrency, not only message throughput, and compare p95 latency and memory with compression disabled.

## Gotchas

Compression can increase size for tiny payloads and create denial-of-service leverage. Context takeover improves ratio but retains state. TLS already protects content in transit but does not remove compression side-channel considerations when secrets and attacker-controlled text share a compression context. Browser control over extension parameters may be limited.

## Sources

- [IETF RFC 7692 — Compression Extensions for WebSocket](https://datatracker.ietf.org/doc/html/rfc7692)
- [IETF RFC 6455 — The WebSocket Protocol](https://datatracker.ietf.org/doc/html/rfc6455)
