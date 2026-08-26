# api-design-anti-patterns

**Issue:** Common API design mistakes + how to avoid them
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your API has 50 endpoints. Each one returns a slightly
different shape. Errors return text instead of JSON. Status
codes are inconsistent (some 200s, some 201s, some 204s for
the same thing). Pagination uses offset in one endpoint,
cursor in another. The mobile team is frustrated.

## Root cause
**API design is hard.** Without a standard, each endpoint
becomes a snowflake. Consistency matters more than
correctness.

**Source:** Microsoft REST API Guidelines:
https://github.com/microsoft/api-guidelines

> "Consistency is the most important quality of an API. ...
> Inconsistency is the primary source of friction for API
> consumers."

## The 10 anti-patterns

### 1. Inconsistent status codes
- **Bad:** One endpoint returns 200 for create, another 201
- **Good:** All creates return 201; all updates return 200;
  all deletes return 204

### 2. Inconsistent error format
- **Bad:** Some endpoints return `{ error: 'message' }`,
  others return `{ message: '...', code: '...' }`, others
  return HTML
- **Good:** One error format for all endpoints (RFC 7807
  Problem Details)

```ts
// RFC 7807
{
  "type": "https://example.com/probs/invalid-email",
  "title": "Invalid email",
  "status": 400,
  "detail": "The email 'a@x' is not a valid email address",
  "instance": "/api/users",
  "errors": [
    { "field": "email", "message": "Invalid format" }
  ]
}
```

### 3. Inconsistent pagination
- **Bad:** One endpoint uses `?page=2&size=20` (offset), another
  uses `?cursor=abc` (cursor), another returns all results
- **Good:** All endpoints use the same pagination pattern
  (preferably cursor-based for stability)

### 4. Inconsistent filtering
- **Bad:** One endpoint uses `?status=active`, another uses
  `?filter[status]=active`, another uses `?q=active`
- **Good:** One filtering syntax (e.g. `?filter[status]=active`)

### 5. Inconsistent field naming
- **Bad:** Mix of `snake_case` and `camelCase`
- **Good:** Pick one (usually `camelCase` for JSON APIs, since
  JavaScript clients are common)

```ts
// ❌ Mixed
{ "user_id": "u_123", "displayName": "Alice" }

// ✅ Consistent
{ "userId": "u_123", "displayName": "Alice" }
```

### 6. Exposing internal IDs
- **Bad:** `/api/users/12345` (database internal ID)
- **Good:** `/api/users/u_2vD3kT1x` (UUID, opaque) or
  `/api/users/alice` (human-readable)

### 7. Not using HTTP methods correctly
- **Bad:** POST for everything (`/api/getUser`, `/api/updateUser`)
- **Good:** GET for reads, POST for creates, PATCH for partial
  updates, DELETE for deletes, PUT for full updates

| Method | Use |
|---|---|
| `GET /users` | List users |
| `GET /users/u_123` | Get one user |
| `POST /users` | Create user |
| `PATCH /users/u_123` | Update user (partial) |
| `PUT /users/u_123` | Update user (full) |
| `DELETE /users/u_123` | Delete user |

### 8. Returning too much data
- **Bad:** `GET /users` returns the user + their posts +
  their comments + their likes (5MB response)
- **Good:** `GET /users` returns just the users. Use
  `?include=posts` to opt in to nested data.

### 9. Not versioning
- **Bad:** Breaking change in `/api/users` field names; all
  clients break
- **Good:** `/api/v1/users` for the old; `/api/v2/users` for
  the new; deprecate the old

### 10. Not documenting
- **Bad:** No docs, the only way to understand the API is to
  read the code
- **Good:** OpenAPI spec, generated from the code

## The "REST maturity model" (Richardson)

Leonard Richardson's model:
- **Level 0:** The swamp of POX (plain old XML over HTTP)
- **Level 1:** Resources (one URL per resource)
- **Level 2:** HTTP verbs (correct use of GET/POST/PATCH/DELETE)
- **Level 3:** Hypermedia controls (HATEOAS)

Most APIs are at Level 2. Level 3 is rare in practice (the
value is debatable for non-public APIs).

## The "REST vs GraphQL" choice

### REST
- ✅ Simple, well-understood
- ✅ Cacheable
- ✅ Tooling everywhere
- ❌ Over-fetching (you get all fields)
- ❌ Under-fetching (you need multiple calls)

### GraphQL
- ✅ Single endpoint, get only what you need
- ✅ Strongly typed
- ❌ Complex tooling
- ❌ Hard to cache
- ❌ N+1 query risk

For most apps, REST is fine. Use GraphQL when:
- The client needs flexible data shapes
- You have multiple clients with very different needs
- The team is willing to invest in GraphQL tooling

## The "OpenAPI" documentation

Generate from code, not by hand:
```ts
// In TypeScript with zod + zod-to-openapi
import { z } from 'zod';
import { extendZodWithOpenApi } from '@asteasolutions/zod-to-openapi';

extendZodWithOpenApi(z);

const UserSchema = z.object({
  id: z.string().openapi({ example: 'u_123' }),
  email: z.string().email().openapi({ example: 'alice@example.com' }),
  displayName: z.string().openapi({ example: 'Alice' }),
});

const userPaths = {
  '/api/users': {
    get: {
      responses: {
        200: {
          description: 'List users',
          content: { 'application/json': { schema: UserSchema.array() } },
        },
      },
    },
  },
};
```

The OpenAPI spec is generated; docs are auto-updated.

## Verification
- **Test:** `test/api.test.ts > every endpoint returns the
  same error format` — passes
- **Test:** `test/api.test.ts > every endpoint uses consistent
  pagination` — passes
- **Audit:** Annual API design review

## Gotchas
- **Consistency is a discipline.** A team of 5 can have 5
  different opinions on how to format a response. A
  documented standard is essential.
- **A linter helps.** ESLint rules for naming, types, etc.
- **The "Postman collection" is documentation.** Maintain it
  as part of the codebase.
- **The "test client" is documentation.** Use the test
  client to demonstrate usage.
- **API design is opinionated.** A consistent "bad" design is
  better than an inconsistent "good" design.

## Related
- `api-versioning.md`
- `api-gateway-pattern.md`
- `api-key-authentication.md`
- `rate-limiting-strategies.md`
- `error-budget-slo.md` (API reliability)
- Microsoft API guidelines: https://github.com/microsoft/api-guidelines
- Zalando REST guidelines: https://opensource.zalando.com/restful-api-guidelines/
- RFC 7807: https://datatracker.ietf.org/doc/html/rfc7807
