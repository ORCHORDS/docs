# async-forEach-silent-no-await

**Issue:** `Array.prototype.forEach` does not await async callbacks, so errors are swallowed and execution continues before async work finishes
**Date:** 2026-08-11
**Status:** documented

## Symptom
Database writes or API calls inside a `forEach` loop appear to succeed but some are skipped. Errors thrown inside the callback are unhandled rejections rather than caught by the surrounding `try/catch`.

## Root cause
`forEach` ignores the return value of its callback. An `async` callback returns a Promise, which `forEach` discards. The loop finishes synchronously; the promises run in the background with no coordination.

## Fix
```ts
// Broken
items.forEach(async (item) => {
  await db.insert(item); // errors silently swallowed
});

// Sequential
for (const item of items) {
  await db.insert(item);
}

// Parallel
await Promise.all(items.map(async (item) => db.insert(item)));
```

## Detection
```
grep -rn "\.forEach(async" src/ --include="*.ts"
```
Every hit is a bug candidate.

## Related
- `promise-all-vs-allsettled.md`
- `node-unhandled-rejection-crash.md`
