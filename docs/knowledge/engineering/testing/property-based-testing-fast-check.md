# property-based-testing-fast-check

**Issue:** Testing properties that hold for all inputs using fast-check
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Example-based tests only check known inputs. Property-based tests generate hundreds of random inputs to find edge cases.

## Pattern / Solution
```bash
npm install -D fast-check
```

```ts
import * as fc from "fast-check";

// Property: reverse of reverse is original
it("double reverse equals original", () => {
  fc.assert(
    fc.property(fc.array(fc.integer()), (arr) => {
      expect([...arr].reverse().reverse()).toEqual(arr);
    })
  );
});

// Property: sorted array is always ordered
it("sort result is always ascending", () => {
  fc.assert(
    fc.property(fc.array(fc.integer({ min: -1000, max: 1000 })), (arr) => {
      const sorted = [...arr].sort((a, b) => a - b);
      for (let i = 0; i < sorted.length - 1; i++) {
        expect(sorted[i]).toBeLessThanOrEqual(sorted[i + 1]);
      }
    })
  );
});

// Reproduce a failure
fc.assert(fc.property(...), { seed: 1234567890 });
```

## Gotchas
- fast-check shrinks failing cases to minimal reproduction
- Default 100 runs — increase with `{ numRuns: 1000 }` for critical code
- Not a replacement for example-based tests — complement them

## Related
- `fuzz-testing-basics.md`
- `unit-test-what-to-test.md`
