# next-js-intercepting-routes

**Issue:** Opening a detail view in a modal while keeping the list page in the background
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Instagram-style photo modal: clicking a photo shows a modal without navigating away; direct URL opens the full page.

## Pattern / Solution
```
app/
  photos/
    page.tsx           <- grid
    [id]/
      page.tsx         <- full photo page (direct URL)
  @modal/
    (.)photos/[id]/
      page.tsx         <- intercepted modal
  layout.tsx           <- renders {children} and {modal}
```
Convention prefixes: (.) same level, (..) one level up, (...) root.

## Gotchas
- Requires a parallel route slot (@modal) in the same layout
- default.tsx in @modal renders null to avoid showing the slot on non-intercepted navigations
- Hard refresh bypasses interception and loads the full page

## Related
- `next-js-parallel-routes.md`
- `react-portal-patterns.md`
