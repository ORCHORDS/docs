# Map.getOrInsertComputed Callbacks Can Reenter the Map

**Issue:** The callback runs only after an initial absence check, but user code can mutate the same Map before the computed value is stored.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Keep the callback pure with respect to the target Map where practical.
- Do not use `getOrInsertComputed` as a lock, single-flight primitive, or atomic database-style insert.
- Validate callback output before it becomes shared cache state.
- Add explicit in-flight coordination for asynchronous or recursive initialization.
- Document key equality and object-identity expectations.

## Verification
- In the callback, insert, delete, clear, recurse on the same key, and mutate another key.
- Test callback throw and proxy/getter side effects in key construction.
- Compare behavior across supported runtimes.

## Gotchas
The method is synchronous and its name does not imply concurrency control. Callback reentrancy can overwrite an intervening value according to the specified steps.

## Official sources
- [ECMAScript Map.getOrInsertComputed](https://tc39.es/ecma262/multipage/keyed-collections.html#sec-map.prototype.getorinsertcomputed)
