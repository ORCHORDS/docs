# typescript-satisfies-vs-as

**Issue:** Using `as` instead of `satisfies` suppresses type errors and loses precise inference
**Date:** 2026-08-11
**Status:** documented

## Symptom
A config object is cast with `as MyConfig` and a misspelled property is silently ignored. Or a function receives the wrong property type at runtime because the cast hid an incompatibility.

## Root cause
`as T` is a type assertion — it tells TypeScript "trust me, this is T" and skips checking. `satisfies T` validates the object against `T` without widening its type, preserving the literal/inferred type for subsequent use.

## Fix
```ts
// Bad — cast hides typo
const config = { retries: 3, timeoutMs: 500, endpont: '/api' } as Config;

// Good — satisfies catches the typo at compile time
const config = { retries: 3, timeoutMs: 500, endpont: '/api' } satisfies Config;
// Error: Object literal may only specify known properties, 'endpont' does not exist
```

## Detection
```
grep -rn " as " src/ --include="*.ts" | grep -v "as const\|as unknown\|as string\|as number"
```
Audit remaining `as` casts to see if `satisfies` is more appropriate.

## Related
- `typescript-const-assertion-inference.md`
- `typescript-enum-reverse-mapping-bug.md`
