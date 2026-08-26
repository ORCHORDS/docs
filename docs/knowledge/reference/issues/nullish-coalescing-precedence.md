# nullish-coalescing-precedence

**Issue:** `??` has lower precedence than `||` and `&&`, causing unexpected grouping when mixed without parentheses
**Date:** 2026-08-11
**Status:** documented

## Symptom
`a || b ?? c` throws a SyntaxError: "Nullish coalescing operator(??) requires parens when mixing with the logical or(||) operators." Or in environments that allow it, the expression evaluates differently than intended.

## Root cause
`??` cannot be mixed directly with `||` or `&&` without explicit parentheses. The spec intentionally requires parens to avoid ambiguity. In loose parsers or old transpilers this may silently evaluate as `(a || b) ?? c` or `a || (b ?? c)` depending on implementation.

## Fix
Always add explicit parentheses:
```ts
// Error or ambiguous
const x = a || b ?? c;

// Explicit — use whichever grouping you intend
const x = (a || b) ?? c;
const x = a || (b ?? c);
```
Use ESLint rule `no-mixed-operators` or `@typescript-eslint/no-mixed-operators` to catch this.

## Detection
```
grep -rn "??" src/ --include="*.ts" | grep "||"
grep -rn "??" src/ --include="*.ts" | grep "&&"
```

## Related
- `optional-chaining-assignment-bug.md`
