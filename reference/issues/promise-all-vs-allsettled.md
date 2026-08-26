# promise-all-vs-allsettled

**Issue:** `Promise.all` fast-fails on the first rejection, silently abandoning other in-flight promises and losing their errors
**Date:** 2026-08-11
**Status:** documented

## Symptom
One of several parallel API calls fails, the `catch` handler runs, but the other calls' results (and errors) are never inspected. Side effects from the other promises continue running uncontrolled.

## Root cause
`Promise.all` rejects as soon as any promise rejects. The other promises are not cancelled (JS has no cancellation built-in); they continue but their results are discarded. Errors from them become unhandled rejections.

## Fix
Use `Promise.allSettled` when you need every result regardless of individual failures:
```ts
const results = await Promise.allSettled([fetchA(), fetchB(), fetchC()]);
for (const result of results) {
  if (result.status === 'rejected') {
    console.error('Failed:', result.reason);
  } else {
    process(result.value);
  }
}
```
Reserve `Promise.all` for cases where any failure should abort the whole operation.

## Detection
```
grep -rn "Promise.all(" src/ --include="*.ts" | grep -v "allSettled"
```
Review each call site: does partial failure need handling?

## Related
- `async-forEach-silent-no-await.md`
- `node-unhandled-rejection-crash.md`
