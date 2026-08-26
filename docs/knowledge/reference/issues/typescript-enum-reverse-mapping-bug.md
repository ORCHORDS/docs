# typescript-enum-reverse-mapping-bug

**Issue:** Numeric TypeScript enums have reverse mappings that pollute `Object.keys()` and `Object.values()` iteration
**Date:** 2026-08-11
**Status:** documented

## Symptom
`Object.keys(MyEnum)` returns twice the expected entries: both `["A", "B", "0", "1"]`. A loop over enum keys processes string keys AND numeric reverse-mapping keys, causing duplicate processing or unexpected string-to-number coercions.

## Root cause
TypeScript numeric enums emit reverse mappings: `{ A: 0, B: 1, 0: "A", 1: "B" }`. String enums do NOT emit reverse mappings and are safe to iterate.

## Fix
Prefer string enums or `as const` objects:
```ts
// Avoid
enum Direction { Up, Down }

// Prefer string enum
enum Direction { Up = 'UP', Down = 'DOWN' }

// Or const object
const Direction = { Up: 'UP', Down: 'DOWN' } as const;
type Direction = typeof Direction[keyof typeof Direction];
```
If you must iterate a numeric enum, filter with `isNaN`:
```ts
const keys = Object.keys(MyEnum).filter(k => isNaN(Number(k)));
```

## Detection
```
grep -rn "enum " src/ --include="*.ts" | grep -v "= '"
```
Flags numeric enums (no string assignment).

## Related
- `typescript-const-assertion-inference.md`
- `typescript-satisfies-vs-as.md`
