# Rate-Limit Reset Is a Hint, Not a Shared Clock

**Issue:** Clients that convert a server’s reset timestamp directly into a local delay can retry immediately or wait too long when clocks differ, headers are stale, or multiple intermediaries enforce different limits.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Prefer server-provided relative delay semantics when available and bound every wait locally.
- Add jitter and coordinate retries across workers sharing the same quota.
- Treat RateLimit fields as advisory state for the current policy and scope, not a durable lease.
- Fall back to exponential backoff when fields are absent, invalid, or inconsistent.

## Verification

- Skew the client clock forward and backward while serving the same limit fields.
- Send stale, malformed, contradictory, and intermediary-modified values.
- Run many workers at reset and verify retries do not synchronize into a burst.

## Gotchas

- A reset indication does not promise capacity at that instant.
- Different credentials, routes, or gateways may have different quota scopes.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9331.html
