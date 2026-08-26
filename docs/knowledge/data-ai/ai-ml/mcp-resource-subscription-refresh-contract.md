# MCP Resource Subscription Refresh Contract

**Issue:** Treating a resource update notification as the new resource body causes stale state, missed authorization changes, and reconnect gaps. MCP subscriptions are invalidation signals, not a durable change log.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Negotiate resource capabilities independently: `subscribe` governs URI subscriptions, while `listChanged` governs changes to the resource list.
- Authorize the URI both when processing `resources/subscribe` and again when serving `resources/read`; a subscription must never freeze an old permission decision.
- On `notifications/resources/updated`, re-read the named URI and replace local state atomically. Do not interpret the notification as a patch or assume it carries content.
- Track subscriptions by connection and principal, support `resources/unsubscribe`, and discard server-side subscription state when the session ends.
- Coalesce bursts only as invalidations: at least one successful read after the newest signal must occur. Use an application digest or version if exact change detection is required.
- After reconnect, rebuild desired subscriptions and perform an initial read. The protocol notification stream is not a replayable or durable queue.

## Verification
- Revoke access after subscription and confirm the next read is denied and cached content is removed.
- Disconnect during an update, reconnect, resubscribe, and confirm an initial read converges to current state.
- Send repeated update notifications and verify coalescing never leaves the client on an older successful read.

## Gotchas
A resource-list change and a subscribed resource-content change are separate signals. Supporting one capability does not imply the other.

## Official sources
- https://modelcontextprotocol.io/specification/2025-11-25/server/resources
