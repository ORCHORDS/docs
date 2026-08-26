# browser-performance-api

**Issue:** Measuring real-user performance without relying on external tools
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Lighthouse scores are lab-based; real user experience on various devices is unknown.

## Pattern / Solution
```ts
// Core Web Vitals with web-vitals library
import { onLCP, onINP, onCLS } from 'web-vitals';
onLCP(metric => sendToAnalytics(metric));
onINP(metric => sendToAnalytics(metric));
onCLS(metric => sendToAnalytics(metric));

// Custom timing marks
performance.mark('feature-start');
await doFeatureWork();
performance.mark('feature-end');
performance.measure('feature', 'feature-start', 'feature-end');
const [measure] = performance.getEntriesByName('feature');
console.log(measure.duration);

// Resource timing
const resources = performance.getEntriesByType('resource');
const slowResources = resources.filter(r => r.duration > 500);
```

## Gotchas
- performance.now() is monotonically increasing; not affected by system clock changes
- PerformanceObserver is preferred over getEntries() for ongoing monitoring
- Clear marks with performance.clearMarks() to avoid memory growth

## Related
- `html-web-vitals-inp.md`
- `browser-web-workers.md`
