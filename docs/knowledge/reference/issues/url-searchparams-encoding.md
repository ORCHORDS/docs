# url-searchparams-encoding

**Issue:** `URLSearchParams` encodes spaces as `+` not `%20`, and `+` in values is decoded as a space, causing subtle data corruption
**Date:** 2026-08-11
**Status:** documented

## Symptom
A search query containing a `+` sign (e.g., `C++`) arrives at the server as `C  ` (two spaces). Or a value with spaces is serialized as `hello+world` instead of `hello%20world`, breaking a server that expects RFC 3986 percent-encoding.

## Root cause
`URLSearchParams` uses `application/x-www-form-urlencoded` encoding (HTML form spec), which encodes spaces as `+` and encodes `+` as `%2B`. This differs from RFC 3986 percent-encoding used in path segments and headers.

## Fix
```ts
// URLSearchParams (form encoding — + for space)
new URLSearchParams({ q: 'hello world' }).toString(); // "q=hello+world"

// For RFC 3986 path encoding use encodeURIComponent
`/search?q=${encodeURIComponent('hello world')}`; // "/search?q=hello%20world"

// Decode URLSearchParams correctly
new URLSearchParams('q=hello+world').get('q'); // "hello world" — correct
```
Use `URLSearchParams` for form bodies; use `encodeURIComponent` for URL path/query values that must follow RFC 3986.

## Detection
```
grep -rn "encodeURIComponent\|URLSearchParams" src/ --include="*.ts"
```
Check that the encoding strategy matches what the consumer expects.

## Related
- `formdata-multipart-content-type-auto.md`
- `headers-case-insensitive-but-set-sensitive.md`
