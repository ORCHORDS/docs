# json-parse-silent-nan

**Issue:** `JSON.parse` silently produces `null` or wrong values when the input contains `NaN`, `Infinity`, or `undefined`
**Date:** 2026-08-11
**Status:** documented

## Symptom
A numeric field becomes `null` in the parsed object. Downstream math produces `NaN` without an obvious error. The original serialization was done with `JSON.stringify` on an object that had `NaN` or `Infinity` values.

## Root cause
`JSON.stringify(NaN)` → `"null"`, `JSON.stringify(Infinity)` → `"null"`, `JSON.stringify(undefined)` → property omitted. These are spec-compliant but silent. `JSON.parse("null")` → `null`, not `NaN`.

## Fix
Validate or sanitize before serializing:
```ts
function safeStringify(value: unknown): string {
  return JSON.stringify(value, (_key, val) => {
    if (typeof val === 'number' && !isFinite(val)) {
      throw new Error(`Non-finite number: ${val}`);
    }
    return val;
  });
}
```
Or use a schema library (zod, valibot) to validate the parsed result.

## Detection
```
grep -n "JSON.stringify" src/ -r
```
Look for numeric fields that may originate from division or floating-point operations. Add `Number.isFinite()` guards before serialization.

## Related
- `d1-integer-overflow-javascript.md`
