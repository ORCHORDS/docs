# layout-thrashing-prevention

**Issue:** Interleaved DOM reads and writes cause repeated forced reflows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Layout thrashing occurs when JS reads layout properties then writes to the DOM in a loop. The browser must recalculate layout synchronously on each read, causing 10-100ms delays.

## Pattern / Solution
1. Batch all reads first, then all writes.\n2. Use requestAnimationFrame to schedule writes.\n3. Use FastDOM library to automatically batch reads/writes.\n4. Cache layout values; don't re-read them in loops.

## Gotchas
- getComputedStyle, getBoundingClientRect, offsetWidth/Height, scrollTop all force layout.\n- React's virtual DOM batches updates; direct DOM manipulation in React apps bypasses this.\n- Chrome DevTools shows Forced reflow warnings in the Performance panel.

## Related
dom-manipulation-performance, read-write-batching-dom, requestanimationframe-patterns
