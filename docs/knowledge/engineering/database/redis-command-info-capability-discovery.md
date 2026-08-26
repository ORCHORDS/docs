# Redis command capability discovery

**Issue**

Clients that assume command availability from a version string can fail against modules, managed services, or restricted command sets.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use COMMAND INFO for capability detection where permitted.
- Cache results per connection endpoint and invalidate on topology change.
- Keep a fail-closed fallback for required semantics.

## Verification

1. Test absent, renamed, module, and ACL-denied commands.
2. Exercise failover to different versions.
3. Verify unknown response fields are tolerated.

## Gotchas

- COMMAND may itself be restricted.
- Availability does not grant ACL permission.
- Modules can change command metadata.

## Official source

- [Official documentation](https://redis.io/docs/latest/commands/command-info/)
