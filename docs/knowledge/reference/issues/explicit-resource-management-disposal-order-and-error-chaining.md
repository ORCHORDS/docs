# Explicit Resource Management Disposal Order and Error Chaining

**Issue:** Resources registered with using or await using are disposed in last-in-first-out order. Disposal failures can mask body failures unless SuppressedError and asynchronous completion are handled correctly.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use using only for objects implementing Symbol.dispose and await using for Symbol.asyncDispose or compatible resources.
- Keep acquisition scopes narrow and assume reverse-order disposal.
- Inspect both error and suppressed fields when handling SuppressedError.
- Do not exit or return externally visible success before asynchronous disposal completes.

## Verification

- Acquire multiple resources and assert reverse disposal order.
- Throw in the body and disposer and verify both failures remain observable.
- Exercise partial acquisition where a later constructor fails.

## Gotchas

- A disposer must be safe to call at the defined scope boundary, not at garbage-collection time.
- Await using may introduce an asynchronous boundary even when fallback disposal is synchronous.

## Official sources

- https://tc39.es/proposal-explicit-resource-management/
