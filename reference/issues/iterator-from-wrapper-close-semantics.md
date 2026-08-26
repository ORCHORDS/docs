# Preserve Iterator Close Semantics Around Iterator.from

**Issue:** Wrapping an iterator with `Iterator.from()` does not remove ownership obligations. Early termination, callback failure, or adapter code can require the underlying iterator's `return()` path to run.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Define which layer owns closing an iterator and never consume the same stateful iterator from multiple owners.
- Use iterator-helper chains whose terminal operation performs the specified close behavior; custom loops need an explicit `try/finally`.
- Keep `next`, `return`, and `throw` behavior when adapting foreign or resource-backed iterators.
- Make cleanup idempotent because multiple failure paths may converge.
- Avoid returning a partially consumed wrapper as though it represented a fresh iterable.

## Verification

- Use a probe iterator counting `next()` and `return()` calls.
- Test early break, callback throw, invalid yielded result, normal exhaustion, and explicit close.
- Assert files, cursors, locks, or subscriptions held by the source are released.
- Run conformance cases for both native iterator instances and iterator-like objects passed to `Iterator.from`.

## Gotchas

An iterator is usually single-use and stateful, unlike a reusable iterable. Close behavior differs between normal exhaustion and abrupt completion; tests that only exhaust the source miss the leak path.

## Official sources

- [ECMAScript Iterator.from](https://tc39.es/ecma262/multipage/control-abstraction-objects.html#sec-iterator.from)
- [ECMAScript IteratorClose](https://tc39.es/ecma262/multipage/abstract-operations.html#sec-iteratorclose)
