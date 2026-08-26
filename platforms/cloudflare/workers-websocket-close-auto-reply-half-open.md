# Workers WebSocket close auto-reply and half-open boundary

**Issue:** With compatibility date 2026-04-07+, Workers automatically replies to Close frames; proxies needing coordinated half-close must opt into allowHalfOpen.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Pin date/flag, remove redundant close-on-close handlers, use half-open only for a documented proxy state machine, bound timeout.

## Tests

Peer close, simultaneous close, abnormal drop, half-open backend delay, rollback.

## Gotchas

readyState is CLOSED before the normal close handler under automatic behavior.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-04-07-websocket-auto-reply-to-close/
