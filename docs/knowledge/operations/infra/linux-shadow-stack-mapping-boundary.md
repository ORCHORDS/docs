# Linux shadow-stack mapping boundary

**Problem**

User shadow stacks require specialized mappings and architecture support; treating them like ordinary memory can break control-flow protection.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use in runtimes implementing supported control-flow enforcement.

## Controls

- Probe architecture/kernel support.
- Keep mappings private and sized from measured thread requirements.
- Combine with compiler/runtime CET policy.

## Implementation

- Create with `map_shadow_stack` and supported flags.
- Associate lifecycle with the owning thread/runtime.
- Fail closed when protection is required.

## Tests

- Test supported/unsupported CPUs, fork/clone, thread exit, signal handling, overflow, and core dumps.

## Gotchas

- It is architecture-specific.
- A mapping alone does not enable all CET protections.
- Incorrect handling can crash the runtime.

## Official sources

- [Official documentation](https://man7.org/linux/man-pages/man2/map_shadow_stack.2.html)
