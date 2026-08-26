# third-party-script-impact

**Issue:** Third-party scripts degrade performance and reliability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Third-party scripts (analytics, chat, social embeds, ads) are among the most common causes of poor TBT, INP, and LCP. They run on your origin but you don't control them.

## Pattern / Solution
1. Audit with WebPageTest SPOF test or Lighthouse Reduce impact of third-party code.\n2. Load non-critical third-party scripts after load event or on user interaction.\n3. Use async or defer on all third-party script tags.\n4. Proxy third-party requests through your own origin to improve latency and control.\n5. Establish a third-party script policy: require business justification and performance budget.

## Gotchas
- async scripts can still block the main thread when executing; defer is safer.\n- Some tag managers synchronously inject scripts, bypassing your defer attributes.\n- Third-party script failures can crash your entire page if not wrapped in error boundaries.

## Related
tag-manager-performance, analytics-performance-impact, javascript-main-thread, total-blocking-time
