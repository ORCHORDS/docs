# Redis CLIENT NO-TOUCH observation boundary

**Issue**

Diagnostic reads can update LRU/LFU metadata and perturb the eviction state being investigated unless client touch behavior is disabled.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `CLIENT NO-TOUCH ON` only for bounded diagnostic clients.
- Keep application clients on normal semantics.
- Record server/version support and restore client state on reuse.

## Verification

1. Compare object idle/frequency metadata with touching and non-touching reads.
2. Test pooled connection reset.
3. Exercise eviction under representative memory pressure.

## Gotchas

- No-touch changes eviction observation, not command authorization.
- Client state follows the connection.
- Diagnostics can still consume CPU and network.

## Official source

- [Official documentation](https://redis.io/docs/latest/commands/client-no-touch/)
