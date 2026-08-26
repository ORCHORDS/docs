# feature-cookbook-api-design

**Issue:** API design — REST, resources, errors, pagination
**Date:** 2026-08-09
**Status:** documented

## Symptom
You design an API. The team uses it. They complain
about the URL structure. They complain about the
errors. They complain about pagination. You wish you'd
designed it better.

## Root cause
**API design is a craft.** Follow the patterns.

**Source:** RESTful API Design — various.

## The "resource" pattern

For resources, use nouns:
```
/users          # List + create
/users/{id}     # Get + update + delete
/path/to/posts  # Sub-resource
```

Verbs are HTTP methods, not URLs.

## The "HTTP methods" pattern

For HTTP methods:
- **GET:** Read (idempotent, safe)
- **POST:** Create (not idempotent)
- **PUT:** Update (idempotent, full replace)
- **PATCH:** Update (not idempotent, partial)
- **DELETE:** Delete (idempotent)

```ts
// Get
app.get('/users/:id', async (req) => {
  return Response.json(await getUser(req.params.id));
});

// Create
app.post('/users', async (req) => {
  const user = await createUser(req.body);
  return Response.json(user, { status: 201 });
});

// Update
app.patch('/users/:id', async (req) => {
  return Response.json(await updateUser(req.params.id, req.body));
});

// Delete
app.delete('/users/:id', async (req) => {
  await deleteUser(req.params.id);
  return new Response(null, { status: 204 });
});
```

The methods are correct.

## The "status codes" pattern

For status codes:
- **2xx:** Success
  - 200 OK
  - 201 Created
  - 204 No Content
- **3xx:** Redirect
  - 301 Moved Permanently
  - 304 Not Modified
- **4xx:** Client error
  - 400 Bad Request
  - 401 Unauthorized
  - 403 Forbidden
  - 404 Not Found
  - 409 Conflict
  - 422 Unprocessable Entity
  - 429 Too Many Requests
- **5xx:** Server error
  - 500 Internal Server Error
  - 503 Service Unavailable

The status is appropriate.

## The "error format" pattern

For errors, a consistent format:
```json
{
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "The user with id u_123 was not found.",
    "requestId": "req_abc123",
    "details": {
      "userId": "u_123"
    }
  }
}
```

The error is structured.

## The "validation error" pattern

For validation errors:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request body is invalid.",
    "details": {
      "fields": [
        { "path": "email", "message": "Must be a valid email" },
        { "path": "password", "message": "Must be at least 8 characters" }
      ]
    }
  }
}
```

The validation is per-field.

## The "pagination" pattern

For pagination, cursor-based:
```json
{
  "data": [...],
  "pagination": {
    "nextCursor": "eyJpZCI6InBfMTIzIn0=",
    "hasMore": true
  }
}
```

Cursor-based is stable.

**Source:** Stripe API docs.

## The "filter" pattern

For filters, query parameters:
```
/users?status=active&sortBy=createdAt&sortOrder=desc&limit=20&offset=0
```

The filters are query params.

## The "field selection" pattern

For field selection:
```
/users?fields=id,email,displayName
```

The client selects fields (sparse fieldsets).

## The "batch" pattern

For batch operations:
```
POST /users/batch
{
  "operations": [
    { "method": "create", "data": {...} },
    { "method": "update", "id": "u_1", "data": {...} },
    { "method": "delete", "id": "u_2" }
  ]
}
```

The batch is one request.

## The "idempotency" pattern

For idempotency, use a key:
```ts
app.post('/users', async (req) => {
  const idempotencyKey = req.headers.get('idempotency-key');
  if (idempotencyKey) {
    const cached = await env.KV!.get(`idempotency:${idempotencyKey}`);
    if (cached) return new Response(cached);
  }

  const user = await createUser(req.body);
  const response = new Response(JSON.stringify(user), { status: 201 });

  if (idempotencyKey) {
    await env.KV!.put(`idempotency:${idempotencyKey}`, JSON.stringify(user), { expirationTtl: 86400 });
  }

  return response;
});
```

The endpoint is idempotent.

## The "API key" pattern

For API key auth:
```ts
app.use('*', async (req) => {
  const apiKey = <redacted-secret>'x-api-key');
  if (!apiKey) {
    return new Response('Unauthorized', { status: 401 });
  }

  const user = await lookupApiKey(apiKey);
  if (!user) {
    return new Response('Invalid API key', { status: 401 });
  }

  return null;  // Continue
});
```

The API key is verified.

## The "rate limiting" pattern

For rate limiting headers:
```ts
response.headers.set('RateLimit-Limit', '100');
response.headers.set('RateLimit-Remaining', '50');
response.headers.set('RateLimit-Reset', '60');
```

**Source:** IETF RateLimit:
https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/

## The "versioning" pattern

For versioning, URL-based:
```
/api/v1/users
/api/v2/users
```

URL versioning is the most maintainable.

## The "content negotiation" pattern

For content negotiation:
```ts
const accept = request.headers.get('accept') ?? 'application/json';
if (!accept.includes('application/json')) {
  return new Response('Not Acceptable', { status: 406 });
}
```

The client requests the format.

## The "caching" pattern

For caching headers:
```ts
response.headers.set('cache-control', 'public, max-age=300, s-maxage=600');
response.headers.set('etag', generateEtag(data));
```

The cache headers are set.

**Source:** MDN — HTTP caching:
https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching

## The "CORS" pattern

For CORS:
```ts
response.headers.set('access-control-allow-origin', 'https://app.example.com');
response.headers.set('access-control-allow-methods', 'GET, POST, PATCH, DELETE');
response.headers.set('access-control-allow-headers', 'content-type, authorization');
response.headers.set('access-control-max-age', '86400');
```

The CORS headers are set.

**Source:** MDN — CORS:
https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS

## The "API anti-pattern" anti-patterns

### 1. Verbs in URLs
- **Issue:** `/createUser` is not RESTful
- **Fix:** Use HTTP methods

### 2. Wrong status code
- **Issue:** 200 for errors
- **Fix:** Use 4xx/5xx

### 3. Inconsistent errors
- **Issue:** Different formats per endpoint
- **Fix:** One error format

### 4. No pagination
- **Issue:** Return all rows
- **Fix:** Cursor-based pagination

### 5. No idempotency
- **Issue:** Retries do the work twice
- **Fix:** Idempotency keys

### 6. No rate limit
- **Issue:** Abuse kills the API
- **Fix:** Rate limiting

### 7. No CORS
- **Issue:** Browser blocks the request
- **Fix:** Set CORS headers

## Verification
- **Test:** Status codes are correct
- **Test:** Errors are structured
- **Test:** Pagination works
- **Test:** Idempotency works
- **Live:** API is monitored
- **Audit:** Quarterly API review

## Gotchas
- **The "verbs in URLs" anti-pattern.** Use HTTP
  methods.
- **The "wrong status code" anti-pattern.** Use 4xx/5xx.
- **The "no idempotency" anti-pattern.** Use idempotency
  keys.

## Related
- `api-design-best-practices.md`
- `api-design-anti-patterns.md`
- `api-versioning.md`
- `api-rate-limiting-detail.md`
- `feature-cookbook-pagination.md`
- REST: https://restfulapi.net/
- IETF RateLimit: https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/
- MDN HTTP: https://developer.mozilla.org/en-US/docs/Web/HTTP
