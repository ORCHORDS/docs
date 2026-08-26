# inp-optimization

**Issue:** Interaction to Next Paint exceeds 200ms
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
INP replaced FID in March 2024 as a Core Web Vital. It measures the worst interaction latency (p98) across clicks, taps, and keyboard events during a page visit.

## Pattern / Solution
1. Break up long tasks with scheduler.yield() or setTimeout(..., 0) at natural checkpoints.\n2. Defer non-critical event handler work to requestIdleCallback.\n3. Move heavy computation to a Web Worker.\n4. Reduce JavaScript execution time on the main thread.\n5. Use event delegation instead of attaching many individual listeners.

## Gotchas
- INP is a 98th percentile metric; one slow interaction per session can tank the score.\n- React's synchronous re-renders block the main thread; use startTransition for non-urgent updates.\n- pointerdown fires before click; move work there to shave perceived latency.

## Related
core-web-vitals-overview, long-task-detection, scheduler-yield-api, web-worker-offloading, react-startTransition
