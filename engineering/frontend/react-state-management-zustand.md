# react-state-management-zustand

**Issue:** Global state with React context becomes unwieldy at scale
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Context re-renders entire subtrees; Redux boilerplate is excessive for mid-size apps.

## Pattern / Solution
```ts
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { persist } from 'zustand/middleware';

const useStore = create()(
  persist(
    immer((set) => ({
      bears: 0,
      addBear: () => set((s) => { s.bears++; }),
    })),
    { name: 'bear-storage' }
  )
);

// Always use selectors to avoid unnecessary re-renders
const bears = useStore((s) => s.bears);
```

## Gotchas
- Subscribing to the whole store re-renders on any change; always use selectors
- immer middleware required for safe mutation of nested state
- Add devtools middleware for Redux DevTools support

## Related
- `react-state-management-jotai.md`
- `react-context-performance.md`
