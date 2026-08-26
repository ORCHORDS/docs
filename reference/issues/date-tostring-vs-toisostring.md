# date-tostring-vs-toisostring

**Issue:** `Date.toString()` returns a locale/implementation-specific string; `toISOString()` is the portable serialization form
**Date:** 2026-08-11
**Status:** documented

## Symptom
A date is stored or compared as a string using `.toString()`. In different environments (browser vs. Node vs. Cloudflare Workers) the string format differs. String comparison or parsing breaks across environments.

## Root cause
`Date.prototype.toString()` is implementation-defined. It typically returns something like `"Tue Aug 11 2026 15:30:00 GMT+0200 (Central European Summer Time)"`, which varies by runtime and locale. `toISOString()` always returns `"2026-08-11T13:30:00.000Z"` (UTC, ISO 8601).

## Fix
```ts
// Avoid
const stored = new Date().toString(); // non-portable

// Use
const stored = new Date().toISOString(); // always ISO 8601 UTC

// For display, use Intl.DateTimeFormat with explicit locale and timezone
new Intl.DateTimeFormat('en-US', { timeZone: 'UTC' }).format(new Date());
```

## Detection
```
grep -rn "\.toString()" src/ --include="*.ts" | grep -i "date\|Date"
```

## Related
- `date-timezone-implicit-local.md`
