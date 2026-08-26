# Node Stream finished Listener Cleanup

**Issue:** Repeatedly awaiting stream completion can accumulate listeners because Node intentionally leaves `error`, `end`, `finish`, and `close` listeners after `finished()` reports completion.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- For callback-style `stream.finished()`, retain and call the returned cleanup function when the stream's later errors no longer need to be observed.
- For `stream/promises.finished()`, enable its cleanup option when listener retention is not required by the surrounding lifecycle.
- Use one watcher per lifecycle and remove application listeners in `finally`; do not attach a fresh watcher inside an unbounded polling loop.
- Treat an `AbortSignal` as cancellation of the wait only. Destroy or otherwise cancel the underlying stream separately when that is the desired behavior.
- Set explicit listener-count alerts and investigate rather than raising the global maximum listener limit.
- Define whether a stream is single-use or reusable; cleanup and late-error handling differ between those contracts.

## Verification
- Run thousands of completed, failed, and aborted streams and assert listener counts return to the expected baseline.
- Emit a late error after the completion callback in a controlled test and confirm the selected cleanup policy behaves intentionally.
- Abort the watcher and verify whether the underlying stream continues or is explicitly destroyed as designed.

## Gotchas
Removing listeners too early can turn a later stream error into an unhandled error. Cleanup must follow an explicit ownership decision, not a blanket rule.

## Official sources
- https://nodejs.org/api/stream.html
