# typescript-narrowing-after-null-check

**Issue:** TypeScript narrows `ctx` to `never` inside `if (!ctx)` block — optional chaining fails
**Date:** 2026-08-11
**Status:** documented

## Symptom

```typescript
const ctx = await authenticate(request, env);
if (!ctx) return problemJson(401, ..., ctx?.request_id);
//                                     ^^^^^^
// Error: Object is of type 'never'. ts(2571)
```

TypeScript's control flow analysis narrows `ctx` to `never` inside the `if (!ctx)` branch
because, by definition, `ctx` is falsy here. Accessing `ctx?.request_id` in that branch
is a type error — TypeScript knows `ctx` can never be truthy at that point.

This is technically correct but surprising when you want a fallback value.

## Fix — use `undefined` directly

The `request_id` is only needed for logging/tracing. When ctx is null, there's no request_id:

```typescript
if (!ctx) return jsonError(401, 'unauthorized', undefined, undefined);
```

The fourth argument to `jsonError` is `request_id?: string`. Passing `undefined` is correct
and omits the request_id from the response — which is fine for unauthenticated requests.

## Why not `ctx?.request_id`?

`ctx?.request_id` would mean "if ctx is non-null, get request_id". Inside `if (!ctx)`,
ctx is always null/undefined, so this would always be undefined. TypeScript's type narrowing
makes this a compile error to prevent confusing code. The fix (`undefined`) is semantically
identical and explicit.

## Pattern — v1 files (`functions/api/v1/*.ts`)

This pattern appears in all v1 handlers. The correct form:

```typescript
// Wrong:
if (!ctx) return problemJson(401, 'unauthorized', 'Please log in', ctx?.request_id);

// Correct:
if (!ctx) return jsonError(401, 'unauthorized', 'Please log in', undefined);
```

## Batch fix (PowerShell)

To fix all occurrences across multiple files:

```powershell
$files = Get-ChildItem functions/api/v1 -Filter "*.ts" -Recurse
foreach ($f in $files) {
  (Get-Content $f.FullName) -replace 'ctx\?\.request_id', 'undefined' |
    Set-Content $f.FullName
}
```

Verify: `npx tsc -p tsconfig.functions.json --noEmit` should exit 0 after this.

## Related symptom — `never` in catch blocks

Similar narrowing issue in catch blocks:

```typescript
let body: Body;
try {
  body = await request.json() as Body;
} catch {
  // body is possibly unassigned here if catch re-throws or falls through
}
// Error: Variable 'body' is used before being assigned.
```

Fix: initialize with a default value — `let body: Body = {};` — so it's always assigned.

## Related

- `typescript-route-handler.md`
- `mccontext-gate-pattern.md`
- `error-codes-and-responses.md`
- `pages-functions-routing.md`
