# map-vs-object-key-ordering

**Issue:** Plain objects do not guarantee insertion-order for integer-like keys; `Map` always preserves insertion order
**Date:** 2026-08-11
**Status:** documented

## Symptom
An object used as a map with numeric string keys (`{ "1": "a", "10": "b", "2": "c" }`) iterates in numeric ascending order (`1, 2, 10`), not insertion order, breaking assumptions about ordering.

## Root cause
The ECMAScript spec defines that integer-indexed properties of objects are iterated in numeric ascending order before string keys. Keys like `"1"`, `"2"`, `"10"` qualify as integer indices. `Map` iterates strictly in insertion order for all key types.

## Fix
```ts
// Fragile — integer-like keys reorder
const m: Record<string, string> = {};
m['1'] = 'a'; m['10'] = 'b'; m['2'] = 'c';
Object.keys(m); // ['1', '2', '10']

// Use Map for guaranteed insertion order
const m = new Map<string, string>();
m.set('1', 'a'); m.set('10', 'b'); m.set('2', 'c');
[...m.keys()]; // ['1', '10', '2']
```

## Detection
```
grep -rn "Record<string" src/ --include="*.ts"
```
Audit usages where keys may be numeric strings and insertion order matters.

## Related
- `set-equality-by-reference.md`
- `array-sort-unstable-older-engines.md`
