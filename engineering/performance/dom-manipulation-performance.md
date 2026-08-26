# dom-manipulation-performance

**Issue:** Frequent DOM reads and writes cause layout thrashing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Reading layout properties (offsetWidth, getBoundingClientRect) after DOM changes forces synchronous layout. Interleaving reads and writes in a loop causes layout thrashing.

## Pattern / Solution
1. Batch DOM reads together, then DOM writes together.\n2. Use DocumentFragment for inserting multiple nodes at once.\n3. Hide the element (display: none) while making many changes, then show it.\n4. Use requestAnimationFrame to synchronize DOM writes with the browser paint cycle.\n5. Prefer CSS classes over inline style changes for multiple property updates.

## Gotchas
- innerHTML is fast for large updates but destroys and recreates the subtree, losing event listeners.\n- classList.add/remove is faster than element.style.property = value for multiple changes.\n- Reading scrollTop or scrollLeft also forces layout.

## Related
layout-thrashing-prevention, read-write-batching-dom, requestanimationframe-patterns
