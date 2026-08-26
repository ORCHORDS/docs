# requestanimationframe-patterns

**Issue:** JS animations run out of sync with the browser's paint cycle
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
requestAnimationFrame (rAF) schedules a callback before the next browser paint, ensuring animations are synchronized to the display refresh rate (typically 60 or 120 fps).

## Pattern / Solution
1. Basic animation loop: function animate(timestamp) { update(timestamp); render(); requestAnimationFrame(animate); }.\n2. Cancel with cancelAnimationFrame(handle) when animation ends.\n3. Use timestamp parameter for time-based (not frame-based) animation.\n4. Perform all DOM writes inside rAF; batch DOM reads before the rAF call.

## Gotchas
- rAF callbacks pause when the tab is hidden; handle visibilitychange to pause animations.\n- Nesting multiple rAF loops compounds frame budget; share one loop per page.\n- On 120fps displays, rAF fires twice as often; use time-based animation to stay consistent.

## Related
css-animation-gpu, layout-thrashing-prevention, read-write-batching-dom
