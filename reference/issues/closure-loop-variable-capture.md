# closure-loop-variable-capture

**Issue:** Closures inside a `var`-declared loop capture the same mutable variable, so all callbacks share the final loop value
**Date:** 2026-08-11
**Status:** documented

## Symptom
A loop registers N click handlers or timeouts; all of them print the same index (the last value of `i`) instead of their individual iteration index.

## Root cause
`var` is function-scoped, not block-scoped. All closures close over the single `i` binding. By the time any callback executes, the loop has finished and `i === N`.

## Fix
Use `let` (block-scoped, new binding per iteration) or an IIFE to capture the current value:
```ts
// Broken
for (var i = 0; i < items.length; i++) {
  setTimeout(() => console.log(i), 0); // always prints items.length
}

// Fixed with let
for (let i = 0; i < items.length; i++) {
  setTimeout(() => console.log(i), 0); // prints 0, 1, 2, ...
}
```

## Detection
```
grep -rn "for (var " src/ --include="*.ts"
```
Also enabled by ESLint rule `no-var`.

## Related
- `memory-leak-event-listener.md`
