# array-sort-unstable-older-engines

**Issue:** `Array.prototype.sort` is not guaranteed stable in engines older than V8 7.0 / Node 11, causing non-deterministic ordering of equal elements
**Date:** 2026-08-11
**Status:** documented

## Symptom
A sorted list of records with equal sort keys appears in different orders across Node versions or browser environments, breaking reproducible tests or pagination.

## Root cause
Prior to V8 7.0 (Node 11 / Chrome 70), `Array.sort` used an unstable QuickSort for arrays longer than 10 elements. Elements with equal keys could appear in any order. ECMAScript 2019 mandated stable sort; modern engines comply.

## Fix
If you must support older engines, implement a stable sort:
```ts
function stableSort<T>(arr: T[], compare: (a: T, b: T) => number): T[] {
  return arr
    .map((item, index) => ({ item, index }))
    .sort((a, b) => compare(a.item, b.item) || a.index - b.index)
    .map(({ item }) => item);
}
```
Or add a tie-breaker to your comparator that references a unique field (e.g., `id`).

## Detection
Check `node --version`. If < 11, sort is potentially unstable. Write a test that sorts an array of objects with equal primary keys and asserts insertion-order stability.

## Related
- `map-vs-object-key-ordering.md`
