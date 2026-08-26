# optional-chaining-assignment-bug

**Issue:** Optional chaining on the left-hand side of an assignment silently does nothing when the chain is nullish
**Date:** 2026-08-11
**Status:** documented

## Symptom
`obj?.nested.value = 42` compiles in some configurations but is a syntax error in strict mode. Or the assignment appears to succeed but the value is never written because an intermediate property was `undefined`.

## Root cause
Optional chaining (`?.`) is only valid on the right-hand side of an assignment. Using it on the left-hand side is a SyntaxError per the ECMAScript spec (`Invalid left-hand side in assignment`). TypeScript (pre-5.x) may emit this as valid JS in some targets, but V8/SpiderMonkey will throw at runtime.

## Fix
Guard explicitly before assigning:
```ts
// Wrong
obj?.nested.value = 42;

// Correct
if (obj) {
  obj.nested.value = 42;
}
// Or use nullish coalescing for defaults
const target = obj ?? { nested: { value: 0 } };
target.nested.value = 42;
```

## Detection
```
grep -rn "?\." src/ --include="*.ts" | grep "= " | grep -v "=="
```
Manually audit hits for left-hand-side optional chains.

## Related
- `nullish-coalescing-precedence.md`
