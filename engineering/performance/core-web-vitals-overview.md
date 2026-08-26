# core-web-vitals-overview

**Issue:** Understanding the three Core Web Vitals metrics and how they affect search ranking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Pages underperform in search rankings and users report slow or janky experiences. Google uses CWV as ranking signals.

## Pattern / Solution
Core Web Vitals are three field metrics measured by Chrome:
- **LCP** (Largest Contentful Paint): loading performance, target < 2.5s
- **INP** (Interaction to Next Paint): responsiveness, target < 200ms
- **CLS** (Cumulative Layout Shift): visual stability, target < 0.1

```js
// Measure with web-vitals library
import { onLCP, onINP, onCLS } from 'web-vitals';
onLCP(console.log);
onINP(console.log);
onCLS(console.log);
```

## Gotchas
- CWV thresholds use the 75th percentile of field data, not averages
- Lab data (Lighthouse) may differ significantly from field data (CrUX)
- INP replaced FID as a Core Web Vital in March 2024

## Related
- `lcp-optimization.md`
- `inp-optimization.md`
- `cls-prevention.md`
- `crux-field-data.md`
