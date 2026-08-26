# Promise.try Normalizes Synchronous Throw and Async Result

**Issue:** Wrapping a callback as Promise.resolve(callback()) executes the callback before Promise.resolve and therefore lets synchronous exceptions escape instead of becoming rejections.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use Promise.try where supported when invoking a callback that may return a value, thenable, or throw synchronously.
- Keep callback arguments explicit and avoid unnecessary closure capture.
- Handle the returned promise on every path and preserve original error causality.
- Provide a tested compatibility helper for runtimes without Promise.try.

## Verification

- Invoke callbacks that return a value, return a promise, return a hostile thenable, and throw synchronously.
- Verify all failures reach the same rejection path.
- Test subclassed Promise behavior if the library exposes it.

## Gotchas

- Promise.try invokes the callback immediately, not in a later task.
- It normalizes invocation shape but does not cancel the callback.

## Official sources

- https://tc39.es/ecma262/multipage/control-abstraction-objects.html#sec-promise.try
