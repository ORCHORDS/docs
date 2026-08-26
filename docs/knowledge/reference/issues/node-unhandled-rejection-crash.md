# node-unhandled-rejection-crash

**Issue:** An unhandled promise rejection crashes the Node.js process in Node 15+
**Date:** 2026-08-11
**Status:** documented

## Symptom
The process exits with `UnhandledPromiseRejection` and exit code 1 in production. In older Node versions it was only a warning; in Node 15+ it is a fatal crash by default.

## Root cause
A promise rejection has no `.catch()` handler and no rejection handler in a `Promise.all` / `Promise.allSettled` chain. Node emits `unhandledRejection` and, since Node 15, terminates the process.

## Fix
Add a global handler for diagnostics and ensure all rejections are caught:
```ts
process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled rejection at:', promise, 'reason:', reason);
  // Optionally re-throw to crash intentionally with a useful stack
  throw reason;
});
```
Fix the root cause by adding `.catch()` or `try/catch` around every async call that can fail.

## Detection
Run Node with `--trace-warnings` to see the stack trace of every unhandled rejection. Use ESLint rule `@typescript-eslint/no-floating-promises`.

## Related
- `async-forEach-silent-no-await.md`
- `promise-all-vs-allsettled.md`
