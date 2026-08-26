# state-management-patterns

**Issue:** Choosing the right state management approach for the problem scope
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A simple toggle uses Redux; a complex async workflow uses useState — mismatched tools for each problem.

## Pattern / Solution
```
UI state (open/closed, selected tab)    -> useState / useReducer
Shared UI state (sidebar collapse)      -> Zustand atom or Context
Server state (API data, mutations)      -> TanStack Query / SWR
Form state                              -> react-hook-form
URL state (filters, pagination)         -> search params / TanStack Router
Complex async FSM                       -> XState
Global application state                -> Zustand / Jotai
```

Decision flowchart:
1. Is it server data? -> TanStack Query
2. Is it form data? -> react-hook-form
3. Is it local UI state? -> useState
4. Is it shared between distant components? -> Zustand

## Gotchas
- Do not put server data in a global store; use a cache (TanStack Query)
- URL is the best place for shareable state (search, filters, pagination)
- Over-normalising local state into a global store creates coupling

## Related
- `react-state-management-zustand.md`
- `react-query-patterns.md`
