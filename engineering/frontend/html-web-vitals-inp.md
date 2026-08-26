# html-web-vitals-inp

**Issue:** Interaction to Next Paint is poor due to long tasks blocking the main thread
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Clicking a button takes 600ms to visually respond because a large synchronous operation runs in the event handler.

## Pattern / Solution
```ts
// Break long tasks into microtasks
async function processLargeList(items) {
  for (let i = 0; i < items.length; i++) {
    process(items[i]);
    if (i % 50 === 0) {
      await new Promise(r => setTimeout(r, 0)); // yield to browser
    }
  }
}

// Use scheduler.postTask for priority-aware scheduling
await scheduler.postTask(() => heavyComputation(), { priority: 'background' });

// Move heavy work off the main thread
const worker = new Worker('/worker.js');
worker.postMessage(largeData);
```

```
INP targets:
  Good:       <= 200ms
  Needs work: 200ms - 500ms
  Poor:       > 500ms
```

## Gotchas
- INP replaced FID as a Core Web Vital in March 2024
- Third-party scripts often cause INP issues; audit with Chrome DevTools Performance panel
- Debounce/throttle input handlers for scroll and resize

## Related
- `browser-web-workers.md`
- `browser-performance-api.md`
