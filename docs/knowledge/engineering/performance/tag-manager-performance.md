# tag-manager-performance

**Issue:** Tag manager loads dozens of scripts synchronously on every page
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Google Tag Manager and similar tools inject scripts after firing rules. Unconfigured tag managers accumulate tags for abandoned tools, inject synchronously, and add significant main-thread cost.

## Pattern / Solution
1. Audit all active tags; remove unused and orphaned tags.\n2. Set triggers appropriately -- most tags should fire on DOM ready or window load, not immediately.\n3. Use tag sequencing to avoid race conditions without synchronous blocking.\n4. Load GTM itself with async and as late as possible.\n5. Consider server-side tagging (sGTM) to reduce client-side script count.

## Gotchas
- Tag managers bypass your code review; establish an approval process for new tags.\n- Preview/debug mode adds overhead; ensure it's not enabled in production.\n- Some tags override async -- audit tag code or use a CSP to block unexpected scripts.

## Related
third-party-script-impact, analytics-performance-impact, javascript-main-thread
