# Linux mseal memory-mapping hardening

**Issue:** An in-process memory-corruption primitive may alter or unmap security-critical mappings after initialization.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On supported 64-bit Linux systems, use `mseal()` after finalizing immutable mappings that must not be remapped, resized, protected differently, or unmapped. Align and validate the complete VMA range, seal only after relocation and initialization, and treat the operation as irreversible until process exit. Detect kernel support and define fail-closed behavior for processes whose threat model requires sealing.

## Verification

Attempt every blocked memory-management operation on sealed mappings, cover gaps and unaligned inputs, test repeated sealing, fork behavior, unsupported architectures, crash dumps, and upgrade rollback.

## Gotchas

- Pin and test the exact supported version; defaults and feature states can change.
- Preserve reproducible evidence without storing secrets or personal data.
- Define rollback before production rollout.

## Official source

- [Primary documentation](https://docs.kernel.org/userspace-api/mseal.html)
