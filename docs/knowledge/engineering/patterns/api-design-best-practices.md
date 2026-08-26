# api-design-best-practices

**Issue:** REST API design — the right way
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a REST API. The mobile team uses it. They find
endpoints with different shapes, different status codes,
different error formats. The web team also uses it; they
find different issues. You spend more time documenting
workarounds than building features.

## Root cause
**API design is hard.** Without a standard, each
endpoint is a snowflake.

**Source:** Microsoft REST API Guidelines:
https://github.com/microsoft/api-guidelines

> "An API is a user interface for developers. ... It
> should be designed with the same care as a UI."

## The "REST maturity" revisited

A good REST API:
- **Level 1 (Resources):** Each resource has a URL
- **Level 2 (HTTP verbs):** Correct use of GET/POST/PATCH/
  DELETE
- **Bonus: Hypermedia:** (HATEOAS) for self-describing APIs

For most apps, Level 2 is enough.

## The "resource modeling" pattern

A resource is a "thing" in your system:
- `/users` — the collection
- `/users/{id}` — a specific user
- `/path/to/posts` — the user's posts (sub-resource)

```ts
// Endpoints
GET    /api/users              // List users
POST   /api/users              // Create a user
GET    /api/users/{id}         // Get a user
PATCH  /api/users/{id}         // Update a user (partial)
DELETE /api/users/{id}         // Delete a user
GET    /api/path/to/posts   // List user's posts
POST   /api/path/to/posts   // Create a post for the user
```

## The "HTTP verb" choice

| Verb | Use | Idempotent | Safe |
|---|---|---|---|
| **GET** | Read a resource | Yes | Yes |
| **POST** | Create a resource | No | No |
| **PUT** | Replace a resource | Yes | No |
| **PATCH** | Update a resource (partial) | No | No |
| **DELETE** | Delete a resource | Yes | No |
| **HEAD** | Get headers (no body) | Yes | Yes |
| **OPTIONS** | Get allowed methods | Yes | Yes |

Idempotent = same result on multiple calls.
Safe = no side effects.

## The "status code" choice

| Code | Use |
|---|---|
| **200** | OK (GET, PATCH, PUT) |
| **201** | Created (POST) |
| **202** | Accepted (async) |
| **204** | No content (DELETE) |
| **301** | Moved permanently |
| **302** | Found (redirect) |
| **304** | Not modified (caching) |
| **400** | Bad request (validation) |
| **401** | Unauthorized (no auth) |
| **403** | Forbidden (auth but not allowed) |
| **404** | Not found |
| **409** | Conflict (duplicate, state mismatch) |
| **422** | Unprocessable (semantic error) |
| **429** | Too many requests (rate limit) |
| **500** | Internal error |
| **502** | Bad gateway |
| **503** | Service unavailable |
| **504** | Gateway timeout |

## The "request body" pattern

For POST/PUT/PATCH, the body is JSON:
```ts
// Create user
POST /api/users
Content-Type: application/json
{
  "email": "alice@example.com",
  "displayName": "Alice"
}

// Response
201 Created
Location: /api/users/u_123
{
  "id": "u_123",
  "email": "alice@example.com",
  "displayName": "Alice",
  "createdAt": "2026-08-09T14:30:00.000Z"
}
```

## The "pagination" pattern

Use cursor pagination:
```ts
GET /api/posts?cursor=eyJ0IjoxNzIzMjE4NjAwMCwiaWQiOiJwXzEyMyJ9&limit=20

// Response
200 OK
{
  "data": [...],
  "nextCursor": "eyJ0IjoxNzIzMjE4NTk5OSwiaWQiOiJwXzk5OSJ9",
  "hasMore": true
}
```

Avoid offset pagination (slow for deep pages).

## The "filtering and sorting" pattern

```ts
GET /api/posts?status=published&author=alice&sort=createdAt&order=desc&limit=20
```

Use a consistent filter syntax. Validate sort columns
against a whitelist (SQL injection risk).

## The "field selection" pattern

For sparse fieldsets:
```ts
GET /api/users/u_123?fields=id,email,displayName
// Returns only the requested fields
```

This reduces payload size for mobile.

## The "versioning" pattern

Use URL versioning:
```
/api/v1/users
/api/v2/users
```

Or header versioning:
```
GET /api/users
Accept: application/vnd.myapi.v2+json
```

For most APIs, URL versioning is simpler. Header versioning
is for advanced use cases.

## The "error" pattern

Use RFC 7807 (Problem Details):
```json
{
  "type": "https://example.com/probs/invalid-email",
  "title": "Invalid email",
  "status": 400,
  "detail": "The email 'a@x' is not valid",
  "code": "INVALID_EMAIL"
}
```

## The "content negotiation" pattern

Support multiple formats:
```ts
GET /api/users
Accept: application/json  // Default
Accept: application/xml   // For legacy clients
```

For most apps, JSON only is fine. Add other formats if
needed.

## The "OpenAPI" pattern

Document the API in OpenAPI 3.0:
```yaml
openapi: 3.0.0
info:
  title: My API
  version: 1.0.0
paths:
  /api/users:
    get:
      summary: List users
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            maximum: 100
      responses:
        '200':
          description: List of users
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/User'
```

Generate docs from the spec (Swagger UI, Redoc).

## The "deprecation" pattern

For deprecating endpoints:
```ts
response.headers.set('Deprecation', 'true');
response.headers.set('Sunset', '2027-01-01');
response.headers.set('Link', '</api/v2/users>; rel="successor-version"');
```

Clients can detect the deprecation + plan the migration.

## The "rate limiting" pattern

```ts
// Response headers
response.headers.set('X-RateLimit-Limit', '1000');
response.headers.set('X-RateLimit-Remaining', '999');
response.headers.set('X-RateLimit-Reset', '1723218600');

// 429 response
429 Too Many Requests
Retry-After: 60
```

The client knows the limit + when to retry.

## The "CORS" pattern

For cross-origin requests:
```ts
response.headers.set('Access-Control-Allow-Origin', 'https://app.example.com');
response.headers.set('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE');
response.headers.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
response.headers.set('Access-Control-Max-Age', '86400');
```

For credentials:
```ts
response.headers.set('Access-Control-Allow-Credentials', 'true');
// Access-Control-Allow-Origin must be specific (not *)
```

## Verification
- **Test:** Every endpoint returns the expected status + body
- **Live:** OpenAPI docs are deployed + current
- **Audit:** Annual API design review

## Gotchas
- **The "endpoint per use case" anti-pattern.** Don't
  create endpoints for every UI action. Use the standard
  REST verbs.
- **The "verb in the URL" anti-pattern.** `/api/getUser`
  is not REST. Use `GET /api/users/{id}`.
- **The "inconsistent design" anti-pattern.** A new
  endpoint should match the existing patterns. If it
  doesn't, fix the design.
- **The "no docs" anti-pattern.** Every endpoint should be
  in the OpenAPI spec.
- **The "versioning by date" anti-pattern.** Versions
  should be intentional (v1, v2), not by date.

## Related
- `api-design-anti-patterns.md`
- `api-versioning.md`
- `api-gateway-routing.md`
- `error-codes-and-messages.md`
- `cors-pages-functions.md`
- Microsoft API guidelines: https://github.com/microsoft/api-guidelines
- Zalando: https://opensource.zalando.com/restful-api-guidelines/
- OpenAPI: https://www.openapis.org/
