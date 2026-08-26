# prototype-pollution-via-merge

**Issue:** Deep object merge functions allow `__proto__` or `constructor.prototype` keys to pollute the global prototype chain
**Date:** 2026-08-11
**Status:** documented

## Symptom
After merging untrusted user-supplied JSON, all plain objects in the process acquire unexpected properties. `{}.isAdmin` returns `true`. The attack is silent until the polluted property is accessed.

## Root cause
A naive recursive merge does `target[key] = source[key]` for all keys. If `source` contains `{ "__proto__": { "isAdmin": true } }`, the assignment modifies `Object.prototype`, affecting every object.

## Fix
```ts
function safeMerge(target: Record<string, unknown>, source: Record<string, unknown>) {
  for (const key of Object.keys(source)) {
    if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;
    if (typeof source[key] === 'object' && source[key] !== null) {
      target[key] = safeMerge((target[key] as Record<string, unknown>) ?? {}, source[key] as Record<string, unknown>);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}
```
Or use `structuredClone` + `Object.assign` on known-safe shapes.

## Detection
```
grep -rn "merge\|deepMerge\|Object.assign" src/ --include="*.ts"
```
Audit any merge that accepts user-supplied data.

## Related
- `structuredclone-vs-json-roundtrip.md`
