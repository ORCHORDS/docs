# typescript-template-literal-union-too-wide

**Issue:** Template literal type over a large union produces a type with thousands of members, slowing the compiler or crashing it
**Date:** 2026-08-11
**Status:** documented

## Symptom
`tsc` hangs, reports "Type instantiation is excessively deep and possibly infinite," or produces an error about union types exceeding 100,000 members when combining two large string unions in a template literal.

## Root cause
Template literal types distribute over unions: `` `${A}_${B}` `` where `A` has 100 members and `B` has 100 members produces 10,000 members. TypeScript has internal limits (~100k) and performance degrades well before that.

## Fix
Narrow the unions before combining them, or use a branded string type instead:
```ts
// Too wide
type EventName = `${Entity}_${Action}`; // 50 × 50 = 2500 members

// Better: branded string
type EventName = string & { __brand: 'EventName' };
function makeEvent(entity: Entity, action: Action): EventName {
  return `${entity}_${action}` as EventName;
}
```

## Detection
`tsc --diagnostics` and check "Instantiation count". If instantiations exceed 1M, look for template literal types over large unions.

## Related
- `typescript-narrowing-after-null-check.md`
- `barrel-file-performance.md`
