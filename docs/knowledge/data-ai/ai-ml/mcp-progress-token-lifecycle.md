# MCP progress-token lifecycle

**Issue:** MCP progress notifications are correlated by a caller-provided token; reuse or out-of-order handling can attach progress to the wrong operation.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Generate unique opaque tokens per request, authorize subscriptions, bound frequency, make percentage/total semantics explicit, retire tokens at completion.

## Tests

Concurrent/reused tokens, decreasing progress, missing total, late notification, cancellation and reconnect.

## Gotchas

Progress is advisory and may be dropped; it is not proof of commit or completion.

## Official sources

- https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress
