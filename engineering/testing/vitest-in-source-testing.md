# vitest-in-source-testing

**Issue:** Writing tests inside source files using Vitest in-source testing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
For utility functions and small modules, maintaining a separate `*.test.ts` file feels like overhead. Vitest supports tests co-located with source.

## Pattern / Solution
```ts
// src/utils/math.ts
export function clamp(n: number, min: number, max: number) {
  return Math.min(Math.max(n, min), max);
}

// In-source tests — stripped from production build
if (import.meta.vitest) {
  const { it, expect } = import.meta.vitest;
  it("clamps to min", () => expect(clamp(-5, 0, 10)).toBe(0));
  it("clamps to max", () => expect(clamp(15, 0, 10)).toBe(10));
  it("passes through in range", () => expect(clamp(5, 0, 10)).toBe(5));
}
```

`vitest.config.ts`:
```ts
test: { includeSource: ["src/**/*.ts"] }
```

`vite.config.ts` (production — strips test code):
```ts
define: { "import.meta.vitest": "undefined" }
```

## Gotchas
- In-source tests are stripped in production builds via `define`
- TypeScript needs `/// <reference types="vitest/importMeta" />` or `vitest/globals` in tsconfig types
- Don't use for complex tests that need heavy mocking

## Related
- `vitest-setup.md`
- `unit-test-what-to-test.md`
