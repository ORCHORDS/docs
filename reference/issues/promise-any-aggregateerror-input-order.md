# Promise.any AggregateError preserves input order

**Issue:** Failure diagnostics from `Promise.any()` are correlated by rejection completion time, but `AggregateError.errors` is assembled in original input order, producing the wrong provider, endpoint, or retry attribution.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Contract

`Promise.any(iterable)` fulfills with the first input to fulfill. It rejects only after every input rejects, using an `AggregateError`. The specification stores each rejection reason at the index assigned while consuming the iterable, so `error.errors` follows input order even when operations reject in a different temporal order. An empty iterable rejects with an AggregateError containing no reasons.

## Controls

- Attach immutable operation metadata before building the iterable; do not infer identity from completion order.
- Normalize non-Error rejection reasons at the boundary without discarding the original value.
- Preserve the input index, provider, endpoint, attempt ID, and start time in each wrapped rejection.
- Set per-attempt deadlines and an overall deadline; `Promise.any()` does not provide cancellation.
- Abort or safely drain losing operations after a winner fulfills.
- Redact tokens, URLs, personal data, and response bodies before aggregating or logging failures.
- Bound fan-out and retry budgets so a fast-success strategy does not become a denial-of-wallet pattern.

## Verification

```js
import assert from "node:assert/strict";

const laterFirstInput = new Promise((_, reject) =>
  setTimeout(() => reject("input-0"), 20));
const earlierSecondInput = Promise.reject("input-1");

await assert.rejects(
  Promise.any([laterFirstInput, earlierSecondInput]),
  (error) => {
    assert(error instanceof AggregateError);
    assert.deepEqual(error.errors, ["input-0", "input-1"]);
    return true;
  },
);
```

Also test a winner, all failures, an empty iterable, synchronous thenables, duplicate providers, cancellation, and stable redaction.

## Gotchas

“First” means first fulfillment, not first settled result. A quick rejection does not win. `Promise.any()` does not stop already-running inputs when one fulfills, and aggregation can retain large error objects until the final rejection.

## Official sources

- [ECMA-262, 17th edition: Promise.any](https://262.ecma-international.org/17.0/#sec-promise.any)
- [ECMA-262: PerformPromiseAny](https://262.ecma-international.org/17.0/#sec-performpromiseany)
