# jest-timer-fakes

**Issue:** Testing code that uses setTimeout, setInterval, or Date.now()
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests that actually wait for real timers are slow and flaky. Tests using `Date.now()` return different values each run.

## Pattern / Solution
```ts
beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

it("debounces the search call", () => {
  const search = jest.fn();
  const debounced = debounce(search, 300);

  debounced("query");
  expect(search).not.toHaveBeenCalled();

  jest.advanceTimersByTime(300);
  expect(search).toHaveBeenCalledWith("query");
});

// Fixed Date
it("formats expiry correctly", () => {
  jest.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  expect(formatExpiry(30)).toBe("2026-01-31");
});
```

Run all pending timers: `jest.runAllTimers()`.
Run only next tick: `jest.runOnlyPendingTimers()`.

## Gotchas
- Fake timers affect `Date`, `setTimeout`, and `setInterval` globally
- `jest.runAllTimers()` can infinite-loop with recursive timers
- Restore real timers before async operations in afterEach

## Related
- `jest-module-mocking.md`
- `vitest-setup.md`
