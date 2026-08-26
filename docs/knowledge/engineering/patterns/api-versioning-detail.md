# api-versioning-detail

**Issue:** API versioning — when, how, what to change
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship API v1. Clients build apps on it. You change a
field name in the database. The API returns the new
field. The client's app breaks. The client is angry. You
promise "we'll never break v1 again" — and then you do.

## Root cause
**APIs change. Clients need stability.** The only way to
have both is versioning.

**Source:** Stripe API versioning:
https://stripe.com/docs/api/versioning

> "Stripe API versioning is a way to evolve the API
> without breaking existing integrations."

## The "breaking vs non-breaking" decision

A change is **breaking** if it requires a client to
update. A change is **non-breaking** if clients work
unchanged.

### Breaking changes
- ❌ Removing a field
- ❌ Renaming a field
- ❌ Changing a field's type
- ❌ Adding a new required field
- ❌ Changing the response shape
- ❌ Changing the status code for the same scenario
- ❌ Changing the error format
- ❌ Removing an endpoint
- ❌ Tightening auth (e.g. adding required scope)

### Non-breaking changes
- ✅ Adding a new optional field
- ✅ Adding a new endpoint
- ✅ Adding a new optional query parameter
- ✅ Loosening auth (e.g. allowing new grant type)
- ✅ Performance improvements
- ✅ Adding a new variant to an enum (with default)

For non-breaking changes, ship immediately. For breaking
changes, version.

## The "versioning" strategies

### URL versioning (`/api/v1/users`)
- **Pros:** Simple, visible
- **Cons:** URL changes
- **Use:** Most public APIs

### Header versioning (`Accept: application/vnd.myapi.v2+json`)
- **Pros:** URL is stable
- **Cons:** Less visible; harder to test
- **Use:** When URL is part of the identity

### Query parameter (`?api-version=2`)
- **Pros:** Simple
- **Cons:** Easy to forget; cache issues
- **Use:** Internal APIs

For most apps, **URL versioning** is the right choice.

## The "versioning" pattern

```ts
// v1
app.get('/api/v1/users', v1GetUsers);
app.post('/api/v1/users', v1CreateUser);

// v2 (new shape)
app.get('/api/v2/users', v2GetUsers);
app.post('/api/v2/users', v2CreateUser);

// Shared handlers
async function getUsers(req: Request, env: Env): Promise<User[]> {
  return env.DB!.prepare(`SELECT * FROM users WHERE tenant_id = ?`).bind(req.tenant.id).all<User[]>().then(r => r.results);
}

// v1 response
function v1GetUsers(req: Request, env: Env): Response {
  const users = await getUsers(req, env);
  return jsonOk(users.map(u => ({ id: u.id, email: u.email })));  // Old shape
}

// v2 response
function v2GetUsers(req: Request, env: Env): Response {
  const users = await getUsers(req, env);
  return jsonOk(users.map(u => ({ userId: u.id, emailAddress: u.email, displayName: u.displayName })));  // New shape
}
```

The shared logic is reused; only the response shape
differs.

## The "deprecation" pattern

For deprecating v1:
```ts
// In the v1 response
response.headers.set('Deprecation', 'true');
response.headers.set('Sunset', '2027-01-01');
response.headers.set('Link', '</api/v2/users>; rel="successor-version"');
```

Clients can detect the deprecation + plan the migration.

## The "deprecation timeline"

For a typical deprecation:
- **Day 0:** Announce deprecation (email, blog, dashboard)
- **Day 30:** Add `Deprecation: true` header
- **Day 90:** Add `Sunset: 2026-01-01` header
- **Day 180:** Sunset (return 410 Gone for v1)
- **Day 365:** Remove v1 code

The timeline gives clients 6-12 months to migrate.

## The "version compatibility matrix" pattern

For a major version, document what changed:
```markdown
## v2 breaking changes

### Removed
- `user.email` → use `user.emailAddress`

### Renamed
- `id` → `userId` in all responses
- `created` → `createdAt` in all responses

### Changed types
- `role`: was string, now enum ('viewer', 'admin', 'owner')

### New
- `displayName` (required)
- `phoneNumber` (optional)
```

The matrix is the migration guide.

## The "version negotiation" pattern

For multiple versions supported at once:
```ts
function getVersion(request: Request): 'v1' | 'v2' {
  // URL path
  const url = new URL(request.url);
  if (url.pathname.startsWith('/api/v2/')) return 'v2';
  if (url.pathname.startsWith('/api/v1/')) return 'v1';

  // Default
  return 'v2';
}
```

The version is determined from the request.

## The "version in the OpenAPI" pattern

```yaml
openapi: 3.0.0
info:
  title: My API
  version: 2.0.0
paths:
  /api/v2/users:
    get:
      # v2 spec
  /api/v1/users:
    get:
      # v1 spec
```

The OpenAPI doc has both versions.

## The "versioning trade-offs"

| Strategy | Pros | Cons |
|---|---|---|
| **URL** | Simple, visible | URL changes |
| **Header** | URL stable | Less visible |
| **Query param** | Simple | Cache issues |
| **No versioning** | Simple | Breaking changes break clients |

For most apps, **URL versioning** is the right balance.

## The "graphQL" alternative

For GraphQL, versioning is different:
- The schema is the API
- Deprecate fields (don't remove)
- The schema can grow without breaking

```graphql
type User {
  id: ID!
  email: String! @deprecated(reason: "Use emailAddress")
  emailAddress: String!
}
```

The client can migrate gradually; the old field still
works.

## The "version" anti-patterns

### 1. Version everything
- **Symptom:** Every change gets a new version
- **Why it's wrong:** Maintenance burden; client confusion
- **Fix:** Only version breaking changes

### 2. Never version
- **Symptom:** Breaking changes ship without versioning
- **Why it's wrong:** Clients break; trust is lost
- **Fix:** Always version breaking changes

### 3. Version in the URL forever
- **Symptom:** `/api/v1/`, `/api/v2/`, `/api/v3/`...
- **Why it's wrong:** Maintenance burden; client confusion
- **Fix:** Sunset old versions

### 4. Version the resource, not the API
- **Symptom:** `/api/users-v2/{id}` (version per resource)
- **Why it's wrong:** Inconsistent; hard to maintain
- **Fix:** Version the API

## The "sunset" pattern

For removing a version:
```ts
// 410 Gone response
return new Response(JSON.stringify({
  type: 'https://example.com/probs/gone',
  title: 'API version sunset',
  status: 410,
  detail: 'API v1 was sunset on 2027-01-01. Use v2.',
  code: 'API_V1_SUNSET',
}), {
  status: 410,
  headers: { 'content-type': 'application/problem+json' },
});
```

The client gets a clear "this is gone" message.

## Verification
- **Test:** `test/api-versioning.test.ts > v1 still works
  for old clients` — passes
- **Live:** Old versions are monitored; clients are
  notified
- **Audit:** Annual review of version usage

## Gotchas
- **The "version forever" anti-pattern.** Old versions are
  a maintenance burden. Sunset them.
- **The "version without notice" anti-pattern.** Always
  notify clients of upcoming sunsets.
- **The "version without migration guide" anti-pattern.**
  Breaking changes need a migration guide.
- **The "version in the same URL" anti-pattern.** The
  version is in the URL, not the body.
- **The "version for non-breaking changes" anti-pattern.**
  Non-breaking changes don't need a new version.

## Related
- `api-design-best-practices.md`
- `api-design-anti-patterns.md`
- `error-codes-and-messages.md`
- `documentation-as-code.md`
- Stripe: https://stripe.com/docs/api/versioning
- Microsoft: https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design
