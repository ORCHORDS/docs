# typescript-const-assertion-inference

**Issue:** Without `as const`, TypeScript widens literal types, causing union discriminants to not narrow correctly
**Date:** 2026-08-11
**Status:** documented

## Symptom
A discriminated union switch statement falls through to the `default` branch even for known variants. TypeScript infers `{ type: string }` instead of `{ type: "success" }` because the object literal was not asserted `as const`.

## Root cause
`const x = { type: 'success', data: 42 }` → TypeScript infers `{ type: string; data: number }`. Adding `as const` produces `{ readonly type: 'success'; readonly data: 42 }`, which participates correctly in discriminated union narrowing.

## Fix
```ts
// Without as const — type is widened
const result = { type: 'success', value: 42 };
// result.type is `string`, not `'success'`

// With as const — literal type is preserved
const result = { type: 'success', value: 42 } as const;
// result.type is `'success'`
```
For function returns that feed a discriminated union, ensure the return type is explicit or use `as const` on the returned object.

## Detection
```
grep -rn "type: '" src/ --include="*.ts" | grep -v "as const"
```
Inspect switch statements over union discriminants that hit `default` unexpectedly.

## Related
- `typescript-satisfies-vs-as.md`
- `typescript-enum-reverse-mapping-bug.md`
