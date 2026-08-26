# resize-observer-performance

**Issue:** window resize events trigger expensive layout calculations on every event
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ResizeObserver watches element size changes without listening to window resize events. It fires after layout and before paint, providing size information without forcing reflow.

## Pattern / Solution
1. Create ResizeObserver with a callback receiving entries.\n2. Access entry.contentRect.width and height for the new dimensions.\n3. Use for responsive components that need to react to their own container size.\n4. Debounce the callback if updates are expensive.\n5. Disconnect when the component is destroyed.

## Gotchas
- ResizeObserver delivers observations asynchronously; don't expect synchronous sizing after DOM changes.\n- Avoid mutating observed elements inside the callback -- it can cause infinite loops.\n- Use entry.borderBoxSize for padding-inclusive dimensions (modern API).

## Related
intersection-observer-performance, layout-thrashing-prevention, dom-manipulation-performance
