# jsonok-201-silent-bug

**Issue:** `jsonOk({ id }, 201)` silently returns 200 with `x-request-id: "201"`
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main (also affects a sibling repo, fixed in PR da55e47)
**Author:** the platform team
**Status:** documented (the bug pattern, not yet fixed in the platform)

## Symptom
```ts
return jsonOk({ id: cid }, 201);
// Returns: status 200, x-request-id: "201", body: {"id": "cid"}
```

POSTs that should return 201 Created return 200 OK. REST clients
checking for 201 (the standard for POST-creates-a-resource) don't
get the signal they expect. The `x-request-id` header is set to the
literal string "201" — debuggers that look at this header see a
useless value.

## Root cause
`jsonOk` signature is `(data, request_id, init)`. The 2nd arg is a
**string** request_id, not a status code. The 3rd arg is the
`ResponseInit` (which is where `status` lives).

```ts
export function jsonOk(data: unknown, request_id?: string, init?: ResponseInit): Response {
  const headers = new Headers(init?.headers);
  headers.set('content-type', 'application/json; charset=utf-8');
  headers.set('x-request-id', request_id ?? crypto.randomUUID());
  headers.set('cache-control', 'no-store');
  return new Response(JSON.stringify(data), { ...init, headers });
}
```

`jsonOk({ id }, 201)` sets `request_id = "201"`, leaves `init`
undefined → `status` defaults to 200. The caller likely meant
`jsonOk({ id }, undefined, { status: 201 })`.

This is a footgun by design. The signature is positional and the
2nd arg is a string, so any number-as-status-code call is silently
swallowed.

## Fix
Two layers:

### Layer 1: Add a `jsonCreated` helper
```ts
// functions/_lib/auth.ts
export function jsonCreated(data: unknown, request_id?: string): Response {
  return jsonOk(data, request_id, { status: 201 });
}
```

### Layer 2: Refactor all `jsonOk(payload, 201/200)` callsites
```bash
# Find all bad calls
grep -rn "jsonOk(.*, 20[012])" functions/ --include="*.ts"

# Refactor (per file, with test):
#   return jsonOk({ id: cid }, 201);
# becomes:
#   return jsonCreated({ id: cid });
```

76 calls across 28 compliance-critical handlers were refactored in
a sibling repo PR da55e47. The same audit needs to run on the platform

### Layer 3: Document the trap in jsonOk's docstring
```ts
/**
 * jsonOk(data, request_id?, init?) — generic JSON 200 response.
 *
 * NOTE: The 2nd arg is `request_id` (string), NOT a status code.
 * For 201 Created, use `jsonCreated(data)` instead. Passing 201 as
 * the 2nd arg silently sets x-request-id to "201" and returns 200.
 */
export function jsonOk(...) { ... }
```

## Verification
- **Test:** `test/jsonok-201.test.ts > jsonOk({ id }, 201) returns 200`
  — documents the old bug behavior
- **Test:** `test/jsonok-201.test.ts > jsonCreated({ id }) returns 201` — confirms the fix
- **a sibling repo:** PR da55e47 — 78/78 tests pass, 0 lint errors

## Gotchas
- **The bug is silent.** No error, no warning, no log. The only
  symptom is the wrong status code, which REST clients may or may
  not check.
- **A related pattern: `jsonOk(payload, 200)`.** Same bug. `200`
  is the default status, so this is functionally equivalent to
  `jsonOk(payload)` — but with `x-request-id: "200"`. Useless.
- **For 204 No Content, use `new Response(null, { status: 204 })`
  directly.** No body, no `jsonOk` wrapper.
- **Don't add a `jsonUpdated`/`jsonDeleted` etc. The pattern is
  one-off and named helpers are fine; over-helpering is its own
  anti-pattern. `jsonCreated` is the only high-frequency case.

## Related
- a sibling repo PR da55e47 (76-call refactor)
- Pattern: any helper that takes a positional `string|number`
  arg in TS is a footgun. Use named args or overload signatures.
