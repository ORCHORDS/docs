# headers-case-insensitive-but-set-sensitive

**Issue:** HTTP header names are case-insensitive for reading but `Headers.set()` stores them in the case you provide, so duplicates with different cases can coexist
**Date:** 2026-08-11
**Status:** documented

## Symptom
A header set as `X-Request-Id` is not found when looked up as `x-request-id` in some middleware. Or two headers `Content-Type` and `content-type` both appear in the serialized request, causing servers to reject or misparse the request.

## Root cause
The Fetch API `Headers` object is case-insensitive for `.get()` and `.has()` (per spec). However, older or non-standard implementations (some Node.js `http` module usage, custom header maps) may store and compare headers case-sensitively. Manually building a headers object with a plain `Record<string, string>` is always case-sensitive.

## Fix
Always use the `Headers` class from the Fetch API and rely on its case-insensitive behavior:
```ts
const headers = new Headers();
headers.set('Content-Type', 'application/json');
headers.get('content-type'); // 'application/json' — case-insensitive

// Avoid plain objects where case sensitivity is unclear
const bad: Record<string, string> = { 'Content-Type': 'application/json' };
bad['content-type']; // undefined
```

## Detection
```
grep -rn "headers\['" src/ --include="*.ts"
grep -rn "Record<string, string>" src/ --include="*.ts" | grep -i "header"
```

## Related
- `cors-preflight-missing-headers.md`
- `url-searchparams-encoding.md`
