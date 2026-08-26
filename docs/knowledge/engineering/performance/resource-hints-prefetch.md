# resource-hints-prefetch

**Issue:** Next-page resources not loaded until navigation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
link rel=prefetch fetches a resource at low priority for future use. Ideal for pre-fetching the next page a user is likely to visit.

## Pattern / Solution
1. Prefetch likely next routes: link rel=prefetch href=/checkout as=document.\n2. Prefetch critical JS chunks for routes the user hovers over.\n3. Use quicklink library to automate prefetching in-viewport links.\n4. Prefetch API data for the next page.\n5. Combine with route-level code splitting for maximum effect.

## Gotchas
- Prefetch is low priority; it won't compete with current page resources.\n- Prefetched resources use the user's data quota -- respect navigator.connection.saveData.\n- Do not prefetch resources behind authentication unless the prefetch request also sends credentials.

## Related
resource-hints-preload, resource-hints-preconnect, code-splitting-strategies, dynamic-import-patterns
