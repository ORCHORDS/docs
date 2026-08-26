# Linux mount inventory with listmount and statmount

**Problem**

Text parsing of `/proc/*/mountinfo` is fragile for structured mount inventory and namespace-aware automation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when an agent needs bounded, structured mount discovery on kernels exposing the mount-query syscalls.

## Controls

- Pin minimum kernel and probe syscall support.
- Query within the intended mount namespace and cap returned entries.
- Treat mount IDs as runtime-scoped identifiers, not durable identity.

## Implementation

- Call `listmount()` to enumerate IDs, then `statmount()` for requested fields.
- Fall back to a reviewed parser only when policy allows older kernels.
- Keep authorization separate from inventory.

## Tests

- Test nested namespaces, bind mounts, propagation, rename, unmount races, and unsupported kernels.
- Compare results with `/proc/self/mountinfo` in fixtures.

## Gotchas

- Enumeration can change between calls.
- Seeing a mount does not authorize access.
- Kernel and libc wrapper availability differ.

## Official sources

- [Official documentation](https://man7.org/linux/man-pages/man2/listmount.2.html)
