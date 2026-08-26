# browser-fetch-patterns

**Issue:** fetch error handling is not intuitive; HTTP errors do not reject the promise
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A 404 or 500 response does not trigger the catch block because fetch only rejects on network failure.

## Pattern / Solution
```ts
async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(error.message ?? `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

// With timeout and abort
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 5000);
try {
  const data = await apiFetch('/api/data', { signal: controller.signal });
} finally {
  clearTimeout(timeoutId);
}
```

## Gotchas
- response.json() also returns a promise; await it or chain .then()
- CORS preflight happens automatically; set Access-Control-Allow-Origin on the server
- Credentials: fetch does not send cookies cross-origin by default; use credentials: 'include'

## Related
- `react-useeffect-cleanup.md`
- `browser-permissions-api.md`
