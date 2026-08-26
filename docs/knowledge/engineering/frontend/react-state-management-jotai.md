# react-state-management-jotai

**Issue:** Global store model does not compose well for derived and async state
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Complex derived state or async atoms with Zustand require manual orchestration; Jotai handles this atomically.

## Pattern / Solution
```ts
import { atom, useAtom, useAtomValue } from 'jotai';
import { atomWithQuery } from 'jotai-tanstack-query';

const countAtom = atom(0);
const doubledAtom = atom((get) => get(countAtom) * 2);

const userAtom = atomWithQuery((get) => ({
  queryKey: ['user', get(userIdAtom)],
  queryFn: () => fetchUser(get(userIdAtom)),
}));
```

## Gotchas
- Create atoms outside components; never create inside render
- Use atomFamily for parameterized atoms to avoid duplicates
- Provider-less mode (default) uses a module-level store

## Related
- `react-state-management-zustand.md`
- `react-query-patterns.md`
