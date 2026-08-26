# vitest-module-mock-hoisting

**Issue:** `vi.mock()` calls must be at the top level and are hoisted above imports, so accessing variables defined outside the factory in the mock factory throws a ReferenceError
**Date:** 2026-08-11
**Status:** documented

## Symptom
`ReferenceError: Cannot access 'myVar' before initialization` inside a `vi.mock()` factory. The variable was defined before the `vi.mock()` call in source, but Vitest hoists mock calls to the top of the file before any user code runs.

## Root cause
Vitest uses Babel/AST transforms to hoist `vi.mock()` calls above all `import` statements. This means the mock factory runs before any module-level variable assignments. Closures over `let`/`const` variables fail because those variables are in the temporal dead zone.

## Fix
Use `vi.importMock` or inline the value in the factory, or use `vi.hoisted()`:
```ts
// Broken
const mockFn = vi.fn();
vi.mock('./module', () => ({ fn: mockFn })); // ReferenceError

// Fixed with vi.hoisted
const mockFn = vi.hoisted(() => vi.fn());
vi.mock('./module', () => ({ fn: mockFn }));

// Or inline
vi.mock('./module', () => ({ fn: vi.fn() }));
```

## Detection
```
grep -rn "vi.mock" src/ tests/ --include="*.ts" -A3 | grep -v "vi.fn\|vi.hoisted\|require"
```
Look for variable references inside mock factories that are defined outside them.

## Related
- `jest-esm-transform-config.md`
- `playwright-test-isolation.md`
