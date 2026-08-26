# structuredclone-vs-json-roundtrip

**Issue:** `JSON.parse(JSON.stringify(obj))` loses `Date` objects, `undefined` values, `Map`, `Set`, and circular references; `structuredClone` handles most of these
**Date:** 2026-08-11
**Status:** documented

## Symptom
After a JSON round-trip, `Date` instances become strings. `undefined` properties are dropped. A `Map` becomes `{}`. Circular reference throws `TypeError: Converting circular structure to JSON`.

## Root cause
`JSON.stringify` only handles JSON-native types. Everything else is coerced or dropped. `structuredClone` (available in Node 17+ and all modern browsers) uses the HTML Structured Clone algorithm, which supports `Date`, `Map`, `Set`, `ArrayBuffer`, `RegExp`, and circular references.

## Fix
```ts
// Limited — avoid for deep cloning
const copy = JSON.parse(JSON.stringify(obj));

// Better for plain objects with dates/maps/sets
const copy = structuredClone(obj);

// structuredClone does NOT support: functions, DOM nodes, class instances with methods
```
For class instances, implement a `clone()` method or use a library like `lodash.cloneDeep`.

## Detection
```
grep -rn "JSON.parse(JSON.stringify" src/ --include="*.ts"
```
Each hit is a candidate for `structuredClone`.

## Related
- `json-parse-silent-nan.md`
- `prototype-pollution-via-merge.md`
