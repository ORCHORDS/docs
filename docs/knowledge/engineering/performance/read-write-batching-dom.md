# read-write-batching-dom

**Issue:** DOM reads after writes cause layout invalidation in loops
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A write to DOM style invalidates the browser's layout cache. Reading a layout property after a write forces synchronous layout recalculation. Each such pair in a loop multiplies the cost.

## Pattern / Solution
1. Use requestAnimationFrame to separate read and write phases.\n2. Use the FastDOM library: fastdom.measure(() => { ... }); fastdom.mutate(() => { ... }).\n3. Accumulate writes in an array during read phase; apply all at once.\n4. Consider CSS transitions/animations instead of JS-driven layout changes.

## Gotchas
- Even a single interleaved read/write in an animation loop causes jank at 60fps.\n- Some third-party libraries trigger forced layouts; audit with Performance panel.\n- ResizeObserver callbacks run after layout; safe to read sizes there.

## Related
layout-thrashing-prevention, dom-manipulation-performance, requestanimationframe-patterns
