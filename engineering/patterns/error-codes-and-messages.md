# error-codes-and-messages

**Issue:** Standard error format for APIs — RFC 7807, error codes
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your API returns errors in 5 different formats:
- `{ "error": "message" }`
- `{ "message": "...", "code": "..." }`
- HTML error pages
- Plain text
- `{ "errors": [...] }`

The client team is confused. They write a parser for each
format. They miss one. The app crashes.

## Root cause
**Inconsistent error formats are a UX disaster.** Use a
standard (RFC 7807).

**Source:** RFC 7807 — Problem Details for HTTP APIs:
https://datatracker.ietf.org/doc/html/rfc7807

## The RFC 7807 format

```json
{
  "type": "https://example.com/probs/invalid-email",
  "title": "Invalid email",
  "status": 400,
  "detail": "The email 'a@x' is not a valid email address",
  "instance": "/api/users"
}
```

Fields:
- `type` — A URI that identifies the problem type (docs)
- `title` — A short, human-readable summary
- `status` — The HTTP status code (mirrors the response)
- `detail` — A human-readable explanation
- `instance` — A URI reference identifying the specific
  occurrence

## The "extended" RFC 7807 with error codes

For more context, add custom fields:
```json
{
  "type": "https://example.com/probs/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "The request body is invalid",
  "instance": "/api/users",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Email is not a valid email address"
    },
    {
      "field": "age",
      "code": "OUT_OF_RANGE",
      "message": "Age must be between 18 and 120"
    }
  ]
}
```

The `code` is for machine consumption; `message` is for
humans.

## The "error code" naming convention

For consistent error codes:
- **UPPER_SNAKE_CASE**
- **Specific:** `INVALID_EMAIL` not `INVALID`
- **Descriptive:** `USER_NOT_FOUND` not `NOT_FOUND`

Common patterns:
- `INVALID_INPUT` — generic input error
- `MISSING_REQUIRED_FIELD` — specific field error
- `INVALID_FORMAT` — format error (e.g. email)
- `OUT_OF_RANGE` — value out of range
- `TOO_LONG` / `TOO_SHORT` — length errors
- `NOT_FOUND` — resource not found
- `ALREADY_EXISTS` — duplicate
- `UNAUTHORIZED` — not authenticated
- `FORBIDDEN` — not authorized
- `RATE_LIMITED` — too many requests
- `INTERNAL_ERROR` — server error
- `SERVICE_UNAVAILABLE` — downstream issue

## The "error response" implementation

```ts
interface ApiError {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  code?: string;
  errors?: Array<{ field: string; code: string; message: string }>;
}

function errorResponse(error: ApiError, requestId?: string): Response {
  return new Response(JSON.stringify(error), {
    status: error.status,
    headers: {
      'content-type': 'application/problem+json',  // RFC 7807 content type
      'x-request-id': requestId ?? '',
    },
  });
}

// Usage
return errorResponse({
  type: 'https://example.com/probs/invalid-email',
  title: 'Invalid email',
  status: 400,
  detail: `The email '${input.email}' is not valid`,
  instance: '/api/users',
  code: 'INVALID_EMAIL',
});
```

## The "validation error" pattern

For Zod validation failures:
```ts
import { z } from 'zod';

const UserSchema = z.object({
  email: z.string().email(),
  age: z.number().int().min(18).max(120),
});

function validateInput<T>(schema: z.ZodSchema<T>, input: unknown): { data: T; error: null } | { data: null; error: ApiError } {
  const result = schema.safeParse(input);
  if (result.success) return { data: result.data, error: null };

  const errors = result.error.errors.map(e => ({
    field: e.path.join('.'),
    code: e.code.toUpperCase(),
    message: e.message,
  }));

  return {
    data: null,
    error: {
      type: 'https://example.com/probs/validation-failed',
      title: 'Validation failed',
      status: 400,
      code: 'VALIDATION_FAILED',
      errors,
    },
  };
}
```

## The "exception → error" pattern

For unexpected errors, catch and convert:
```ts
async function handleRequest(request: Request, env: Env): Promise<Response> {
  try {
    return await actualHandler(request, env);
  } catch (err) {
    console.error({ msg: 'unhandled.error', err: String(err), stack: (err as Error).stack });

    // Don't leak internal details to the client
    return errorResponse({
      type: 'https://example.com/probs/internal-error',
      title: 'Internal server error',
      status: 500,
      code: 'INTERNAL_ERROR',
    });
  }
}
```

The client gets a generic 500; the server has the details.

## The "i18n" pattern for errors

For internationalized errors:
```ts
function localizeError(error: ApiError, locale: string): ApiError {
  // Look up the localized message
  const message = i18n.t(`errors.${error.code}`, { locale });
  return { ...error, detail: message };
}
```

The error code is stable; the message is localized.

## The "error code documentation" pattern

For an OpenAPI spec, document the error responses:
```ts
const UserPaths = {
  '/api/users': {
    post: {
      summary: 'Create a user',
      responses: {
        201: { description: 'User created', content: { 'application/json': { schema: UserSchema } } },
        400: { description: 'Validation failed', content: { 'application/problem+json': { schema: ProblemSchema } } },
        401: { description: 'Unauthorized' },
        403: { description: 'Forbidden' },
        409: { description: 'Email already exists' },
        429: { description: 'Rate limited' },
        500: { description: 'Internal error' },
      },
    },
  },
};
```

## The "client handling" pattern

On the client, parse RFC 7807:
```ts
async function handleResponse(res: Response): Promise<unknown> {
  if (res.ok) return res.json();

  if (res.headers.get('content-type')?.includes('application/problem+json')) {
    const problem: ApiError = await res.json();
    throw new ApiException(problem);
  }

  // Fallback
  throw new Error(`HTTP ${res.status}`);
}

class ApiException extends Error {
  constructor(public problem: ApiError) {
    super(problem.detail ?? problem.title);
  }

  get code() { return this.problem.code; }
  get status() { return this.problem.status; }
  get fields() { return this.problem.errors; }
}
```

The client gets a structured error; UI can show field-level
errors.

## The "error logging" pattern

For every error, log the context:
```ts
function logError(error: ApiError, request: Request, env: Env): void {
  console.log({
    timestamp: new Date().toISOString(),
    level: error.status >= 500 ? 'error' : 'warn',
    message: 'api.error',
    code: error.code,
    status: error.status,
    type: error.type,
    path: new URL(request.url).pathname,
    method: request.method,
    requestId: request.headers.get('x-request-id'),
    userId: getUserId(request),
  });
}
```

The log feeds into monitoring (Datadog, Sentry).

## The "error monitoring" pattern

Use Sentry (or similar) for error tracking:
```ts
import * as Sentry from '@sentry/browser';

try {
  // ... do work
} catch (err) {
  Sentry.captureException(err, {
    tags: { code: 'INVALID_EMAIL' },
    extra: { userId, requestId },
  });
  throw err;
}
```

Sentry groups similar errors + alerts on spikes.

## Verification
- **Test:** `test/errors.test.ts > every error response has
  the RFC 7807 format` — passes
- **Test:** `test/errors.test.ts > validation errors list
  every invalid field` — passes
- **Live:** Error rate is monitored; alerts on anomalies

## Gotchas
- **The "leak internal details" gotcha.** A 500 error with
  the SQL query in `detail` is a security bug. Strip
  internal details.
- **The "inconsistent error format" anti-pattern.** Every
  error response must use the same format.
- **The "error code as documentation" anti-pattern.** The
  `code` is for the machine, not a replacement for docs.
  Document the codes.
- **The "i18n in the error code" anti-pattern.** Codes are
  stable identifiers; messages are localized.
- **The "error in error" anti-pattern.** A 500 error that
  itself throws is a debugging nightmare. Make the error
  path robust.

## Related
- `api-design-anti-patterns.md`
- `api-versioning.md`
- `secure-defaults.md`
- RFC 7807: https://datatracker.ietf.org/doc/html/rfc7807
- Zod: https://zod.dev/
- Sentry: https://sentry.io/
