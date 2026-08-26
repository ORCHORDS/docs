# Node Stream pipeline Destroy-and-Reuse Boundary

**Issue:** After `stream.pipeline()` fails, code may attempt to reuse one of its streams or write an HTTP fallback even though pipeline has destroyed components and retained listeners.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Assume pipeline components are single-use after an error. Construct a new stream chain for retries instead of reusing partially consumed or destroyed objects.
- Know the destruction contract: on error, pipeline destroys streams that have not already ended, finished, or closed.
- Remove or account for listeners left by pipeline before reusing any stream; repeated failed reuse can leak listeners and swallow later errors.
- Do not pipeline a request directly into a live HTTP response when an error handler must still write a fallback body; pipeline may destroy the socket first.
- Separate acquisition, transformation, and response commit so failure before headers can produce a controlled response and failure after commit terminates cleanly.
- Propagate one root cause with structured context and avoid secondary writes after the response or destination is closed.

## Verification
- Inject failure before the first chunk, mid-stream, after destination finish, and after response headers; assert destruction and fallback behavior.
- Repeat failed operations and check listener counts, file descriptors, and socket counts for growth.
- Attempt an explicit reuse in a negative test and assert the application rejects it.

## Gotchas
Pipeline simplifies backpressure and teardown, but teardown is intentionally aggressive. It is not a transaction that restores stream state on failure.

## Official sources
- https://nodejs.org/api/stream.html
