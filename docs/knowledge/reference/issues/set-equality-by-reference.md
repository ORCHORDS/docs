# set-equality-by-reference

**Issue:** `Set` and `Map` use reference equality for objects, so two structurally identical objects are treated as different keys
**Date:** 2026-08-11
**Status:** documented

## Symptom
A `Set<object>` contains duplicate entries that look identical when printed. `set.has({ id: 1 })` returns `false` even though `{ id: 1 }` is "in" the set.

## Root cause
`Set` and `Map` use the SameValueZero algorithm, which for objects is reference identity (`===`). Two separately created objects `{ id: 1 }` and `{ id: 1 }` are different references and thus different set members.

## Fix
Use primitive keys derived from the object (e.g., serialized ID):
```ts
// Broken
const seen = new Set<{ id: number }>();
seen.add({ id: 1 });
seen.has({ id: 1 }); // false — different reference

// Fixed — use primitive key
const seen = new Set<number>();
seen.add(item.id);
seen.has(item.id); // true
```
For complex keys, serialize to a canonical string: `JSON.stringify(sortedKeys(obj))`.

## Detection
```
grep -rn "new Set<{" src/ --include="*.ts"
grep -rn "new Map<{" src/ --include="*.ts"
```

## Related
- `map-vs-object-key-ordering.md`
- `structuredclone-vs-json-roundtrip.md`
