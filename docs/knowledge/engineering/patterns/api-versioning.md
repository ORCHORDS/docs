# api-versioning

**Issue:** How to version an API without breaking clients
**Date:** 2026-08-09
**Status:** documented

## Symptom
You change your API response shape. The mobile clients break.
Users see errors. You have no way to roll back without breaking
new clients. The fix: don't break clients.

## Root cause
**An API is a contract with its clients.** Changing the contract
breaks all clients. Without versioning, you can't evolve.

**Source:** Microsoft API design guidelines:
https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design

## The 4 versioning strategies

### 1. URI versioning (`/api/v1/foo`)
```
GET /api/v1/users/123
GET /api/v2/users/123
```

- **Pros:** Easy to see the version, easy to route
- **Cons:** Different URIs for the same resource, harder to
  refactor

### 2. Header versioning (`Accept: application/vnd.api+json; version=2`)
```
GET /api/users/123
Accept: application/vnd.api+json; version=2
```

- **Pros:** Same URI, version is in the contract
- **Cons:** Harder to test in a browser, hidden in headers

### 3. Query parameter (`/api/users/123?v=2`)
- **Pros:** Easy
- **Cons:** Not RESTful, easy to forget

### 4. Content negotiation (`Accept: application/vnd.api.v2+json`)
- **Pros:** Standards-aligned
- **Cons:** Harder to route

## The recommended approach: URI versioning with a deprecation window

```ts
// In your router
export const onRequest: PagesFunction = async (context) => {
  const url = new URL(context.request.url);
  const version = url.pathname.match(/^\/api\/v(\d+)\//)?.[1];

  if (version === '1') {
    return handleV1(context.request, context.env);
  }
  if (version === '2') {
    return handleV2(context.request, context.env);
  }
  return new Response('Not found', { status: 404 });
};
```

V1 and V2 coexist. V1 returns the old response shape; V2 returns
the new. Clients migrate at their own pace.

## Deprecation policy

When a version is deprecated:
1. **Add `Sunset` and `Deprecation` headers** to the response
2. **Document the deprecation** in the API docs
3. **Set a sunset date** (typically 12 months out)
4. **Notify clients** via email + dashboard
5. **Track usage** and reach out to heavy users
6. **Remove the version** after the sunset date

```ts
// On a deprecated endpoint
return new Response(JSON.stringify(data), {
  status: 200,
  headers: {
    'Deprecation': 'true',
    'Sunset': '2027-08-01',
    'Link': '<https://api.example.com/v2/users/123>; rel="successor-version"',
  },
});
```

## Backward-compatible changes (no version bump)

Some changes don't require a new version:
- **Adding an optional field** to the response
- **Adding a new endpoint**
- **Adding a new optional query parameter**
- **Relaxing validation** (e.g. accepting more date formats)

These are backward-compatible. Clients that don't use the new
feature continue to work.

## Breaking changes (require a new version)

- **Removing a field** from the response
- **Renaming a field**
- **Changing a field's type** (e.g. `id` from int to string)
- **Changing the response status code** for a given case
- **Tightening validation** (e.g. rejecting previously-accepted
  input)

These are breaking. New version required.

## Verification
- **Test:** `test/api-versioning.test.ts` — V1 and V2 return
  the right shapes
- **Live:** The deprecated V1 endpoint has `Sunset` and
  `Deprecation` headers
- **Audit:** Quarterly review of API usage + deprecation timeline

## Gotchas
- **Don't deprecate too fast.** 12 months is the industry
  minimum. Some clients (embedded devices, medical devices)
  have multi-year update cycles.
- **Don't version for vanity.** Major version bumps should be
  rare. If you're at v47, your versioning is too granular.
- **The "v1" in the URI is forever.** Once you've shipped
  `/api/v1/...`, that URI is locked. You can add `/api/v2/`,
  `/api/v3/`, etc., but you can't change what v1 means.
- **Internal APIs can use header versioning.** External
  (public) APIs should use URI versioning for visibility.
- **Versioning adds maintenance burden.** Two versions of the
  same endpoint = two code paths to maintain. Deprecate old
  versions aggressively.

## Related
- `patterns/idempotency-keys.md` (orthogonal concern)
- `secrets-rotation-runbook.md` (similar: advance notice +
  backward compatibility)
- Microsoft: https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design
- IETF draft: https://datatracker.ietf.org/doc/draft-ietf-httpapi-api-versioning/
