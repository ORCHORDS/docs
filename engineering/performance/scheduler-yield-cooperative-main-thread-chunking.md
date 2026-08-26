# scheduler.yield Cooperative Main-Thread Chunking

**Issue:** Large synchronous loops and render preparation delay input and paint; naive zero-timeout yielding can lose priority context and still starve important work.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Split work at correctness-safe boundaries and `await scheduler.yield()` between chunks when supported. The continuation defaults to user-visible priority and inherits a surrounding `scheduler.postTask()` priority. Use `postTask` with an abort signal for work needing explicit priority or cancellation.

Measure chunk cost and yield often enough to meet the interaction budget, but not after every trivial operation. Preserve loop state, check cancellation after resumption, and prevent stale continuations from updating a newer view. Provide a tested fallback such as a timer-based task yield; microtasks do not yield to rendering.

Move CPU-heavy, transferable work to a worker rather than endlessly chunking it on the main thread.

## Verification

Profile cold/warm devices, rapid user input, background/user-visible/user-blocking work, cancellation, route changes, hidden tabs, and unsupported browsers. Confirm paints/input occur between chunks, final output is identical, and no stale task commits. Measure INP, long tasks, total completion time, and battery/CPU impact.

## Gotchas

Yielding improves responsiveness but can increase total elapsed time and expose races between chunks. A continuation receives boosted ordering within its priority. `scheduler.yield()` is limited availability and must be feature-detected.

## Sources

- [MDN Scheduler.yield](https://developer.mozilla.org/en-US/docs/Web/API/Scheduler/yield)
- [MDN Prioritized Task Scheduling API](https://developer.mozilla.org/en-US/docs/Web/API/Prioritized_Task_Scheduling_API)
- [WICG Prioritized Task Scheduling](https://wicg.github.io/scheduling-apis/)
