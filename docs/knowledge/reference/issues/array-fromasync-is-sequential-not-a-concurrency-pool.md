# Array.fromAsync Is Sequential, Not a Concurrency Pool

**Issue:** `Array.fromAsync()` awaits values as it consumes an async or sync source and awaits each mapping result. It should not be assumed to schedule mapper work concurrently like `Promise.all()`.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Choose explicitly between ordered sequential consumption and bounded parallel work.
- Use `Array.fromAsync` when backpressure and source order are desired; use a reviewed concurrency limiter when throughput requires parallelism.
- Put cancellation and per-item timeout behavior around the source operation, not only around final array creation.
- Cap or stream unbounded inputs; materializing an iterable necessarily retains the completed array.
- Document mapper side effects because they occur in consumption order.

## Verification

- Instrument active mapper count and assert it never exceeds the intended concurrency.
- Test mapper rejection and iterator cleanup with a source that exposes `return()`.
- Benchmark a realistic slow source so accidental serialization is visible.
- Test an unbounded source under memory limits.

## Gotchas

Passing already-started promises can appear concurrent because work began before consumption. That does not make `Array.fromAsync` a scheduler. A rejected mapper prevents a successfully returned array.

## Official sources

- [ECMAScript Array.fromAsync](https://tc39.es/ecma262/multipage/indexed-collections.html#sec-array.fromasync)
