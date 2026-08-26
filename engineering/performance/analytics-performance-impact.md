# analytics-performance-impact

**Issue:** Analytics scripts measurably degrade Core Web Vitals
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GA4, Segment, Amplitude, and similar tools add JavaScript parse time, main-thread tasks, and network requests. Multiple analytics tools multiply the cost.

## Pattern / Solution
1. Load analytics after TTI using event delegation on first user interaction.\n2. Use the navigator.sendBeacon API for analytics payloads to avoid blocking.\n3. Batch analytics events and flush at visibilitychange to minimize requests.\n4. Prefer lightweight analytics (Plausible, Fathom, Cloudflare Analytics) for simple use cases.\n5. Consolidate to one analytics platform where possible.

## Gotchas
- GA4 uses gtag.js which includes its own measurement protocol; avoid loading gtag AND GA4 separately.\n- Session replay tools (FullStory, Hotjar) are particularly expensive -- assess their value vs. cost.\n- navigator.sendBeacon has a payload limit (~64 KB) and doesn't support custom headers.

## Related
tag-manager-performance, third-party-script-impact, javascript-main-thread
