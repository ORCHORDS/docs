# fetch-no-throw-on-4xx

**Issue:** The Fetch API does not throw on 4xx or 5xx responses; only network errors throw
**Date:** 2026-08-11
**Status:** documented

## Symptom
A 404 or 500 response is treated as a successful fetch. The code reads `response.json()` and gets an error body, then tries to use it as valid data. No exception is raised by `fetch` itself.

## Root cause
`fetch` rejects (throws) only on network-level failures (DNS, TCP). HTTP error status codes (4xx, 5xx) result in a resolved promise with `response.ok === false`. It is the caller's responsibility to check `response.ok` or `response.status`.

## Fix
```ts
async function fetchOrThrow(url: string): Promise<Response> {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`HTTP ${response.status}: ${body}`);
  }
  return response;
}
```

## Detection
```
grep -rn "await fetch(" src/ --include="*.ts" | grep -v "response.ok\|response.status"
```
Any `fetch` call that doesn't check `ok` is a candidate bug.

## Related
- `fetch-body-consumed-twice.md`
- `response-clone-pattern.md`
