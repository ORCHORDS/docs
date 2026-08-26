# API Request Schema Validation with Zod in Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

An API endpoint receives a `POST /users` request with an unexpected field (`role: "admin"`) that bypasses application-level checks and gets persisted to the database. Schema validation was either absent or enforced only in the frontend. The fix is server-side validation at the Workers layer using a typed schema library before any business logic runs.

---

## Context

Zod is the de-facto TypeScript schema validation library. It runs in the Workers runtime without modification (no Node.js built-ins), produces TypeScript types directly from schemas, and supports both parse-or-throw and safe-parse patterns. Key concerns for Workers:

- **Bundle size**: Zod v3 adds ~13 KB gzipped. Zod v4 (mini) reduces this to ~2 KB. Use `zod/mini` for size-sensitive Workers.
- **Performance**: Validation adds <0.5 ms for typical request bodies on Workers (benchmarked at ~50 µs for a 10-field object).
- **Error format**: RFC 7807 Problem Details is the standard error format for REST APIs — Zod's error output must be mapped to it.
- **OpenAPI**: `zod-openapi` or `@asteasolutions/zod-to-openapi` generates OpenAPI 3.1 specs from Zod schemas, keeping API docs in sync with validation logic.

---

## Solution

### Installation

```bash
npm install zod          # v3.x
# OR for smaller bundle:
npm install zod@next     # v4 with zod/mini
```

### Schema Definitions

```typescript
// src/schemas/user.ts
import { z } from 'zod';

export const CreateUserBodySchema = z.object({
  email: z.string().email({ message: 'Must be a valid email address' }),
  name: z.string().min(2).max(100),
  password: z
    .string()
    .min(12, 'Password must be at least 12 characters')
    .regex(/[A-Z]/, 'Must contain an uppercase letter')
    .regex(/[0-9]/, 'Must contain a digit')
    .regex(/[^A-Za-z0-9]/, 'Must contain a special character'),
  // Explicitly whitelist allowed fields — unlisted fields stripped by .strict()
}).strict();

export type CreateUserBody = z.infer<typeof CreateUserBodySchema>;

export const UserIdParamsSchema = z.object({
  userId: z.string().uuid({ message: 'userId must be a valid UUID' }),
});

export const PaginationQuerySchema = z.object({
  // z.coerce converts string query params to the target type
  page:     z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
  sortBy:   z.enum(['createdAt', 'email', 'name']).optional(),
  order:    z.enum(['asc', 'desc']).default('asc'),
});

export type PaginationQuery = z.infer<typeof PaginationQuerySchema>;

export const AuthHeaderSchema = z.object({
  authorization: z
    .string()
    .regex(/^Bearer [A-Za-z0-9._-]+$/, 'Authorization header must be Bearer <token>'),
});
```

### RFC 7807 Problem Details Error Formatter

```typescript
// src/lib/validation-error.ts
import { ZodError, ZodIssue } from 'zod';

interface ProblemDetail {
  type:     string;
  title:    string;
  status:   number;
  detail:   string;
  instance: string;
  errors:   { field: string; message: string; code: string }[];
}

export function zodErrorToProblemDetail(
  error: ZodError,
  instance: string
): ProblemDetail {
  return {
    type:     'https://example.com/problems/validation-error',
    title:    'Validation Error',
    status:   422,
    detail:   `${error.issues.length} validation error(s) occurred.`,
    instance,
    errors:   error.issues.map((issue: ZodIssue) => ({
      field:   issue.path.join('.') || '(root)',
      message: issue.message,
      code:    issue.code,
    })),
  };
}

export function validationErrorResponse(error: ZodError, request: Request): Response {
  const instance = new URL(request.url).pathname;
  const body = zodErrorToProblemDetail(error, instance);
  return new Response(JSON.stringify(body), {
    status: 422,
    headers: {
      'Content-Type': 'application/problem+json',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
```

### Validation Middleware

```typescript
// src/lib/validate-request.ts
import { z, ZodType } from 'zod';
import { validationErrorResponse } from './validation-error';

interface ValidatedRequest<B, Q, P> {
  body: B;
  query: Q;
  params: P;
}

export async function validateRequest<
  B = unknown,
  Q = unknown,
  P = unknown
>(
  request: Request,
  schemas: {
    body?:   ZodType<B>;
    query?:  ZodType<Q>;
    params?: ZodType<P>;
    headers?: ZodType<unknown>;
  },
  routeParams: Record<string, string> = {}
): Promise<
  | { ok: true;  data: ValidatedRequest<B, Q, P> }
  | { ok: false; response: Response }
> {
  // Validate headers
  if (schemas.headers) {
    const headerObj = Object.fromEntries(request.headers.entries());
    const result = schemas.headers.safeParse(headerObj);
    if (!result.success) return { ok: false, response: validationErrorResponse(result.error, request) };
  }

  // Validate body
  let body = undefined as B;
  if (schemas.body) {
    let raw: unknown;
    try {
      raw = await request.json();
    } catch {
      return {
        ok: false,
        response: new Response(
          JSON.stringify({ type: 'https://example.com/problems/parse-error', title: 'JSON Parse Error', status: 400 }),
          { status: 400, headers: { 'Content-Type': 'application/problem+json' } }
        ),
      };
    }
    const result = schemas.body.safeParse(raw);
    if (!result.success) return { ok: false, response: validationErrorResponse(result.error, request) };
    body = result.data;
  }

  // Validate query params
  let query = undefined as Q;
  if (schemas.query) {
    const url = new URL(request.url);
    const queryObj = Object.fromEntries(url.searchParams.entries());
    const result = schemas.query.safeParse(queryObj);
    if (!result.success) return { ok: false, response: validationErrorResponse(result.error, request) };
    query = result.data;
  }

  // Validate route params
  let params = undefined as P;
  if (schemas.params) {
    const result = schemas.params.safeParse(routeParams);
    if (!result.success) return { ok: false, response: validationErrorResponse(result.error, request) };
    params = result.data;
  }

  return { ok: true, data: { body, query, params } };
}
```

### Handler Usage

```typescript
// src/handlers/users.ts
import { validateRequest } from '../lib/validate-request';
import {
  CreateUserBodySchema,
  PaginationQuerySchema,
  UserIdParamsSchema,
  AuthHeaderSchema,
} from '../schemas/user';

export async function handleCreateUser(
  request: Request,
  env: Env,
  routeParams: Record<string, string>
): Promise<Response> {
  const validation = await validateRequest(request, {
    body:    CreateUserBodySchema,
    headers: AuthHeaderSchema,
  });

  if (!validation.ok) return validation.response;

  const { body } = validation.data;
  // body is typed as CreateUserBody — email, name, password only
  // role: "admin" would have been stripped/rejected by .strict()

  // ... proceed with business logic
  return new Response(JSON.stringify({ id: crypto.randomUUID(), email: body.email }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

export async function handleListUsers(
  request: Request,
  env: Env
): Promise<Response> {
  const validation = await validateRequest(request, {
    query: PaginationQuerySchema,
  });
  if (!validation.ok) return validation.response;

  const { page, pageSize, sortBy, order } = validation.data.query;
  // page is number (coerced from string), default 1
  // ... query KV / D1
  return new Response(JSON.stringify({ page, pageSize, items: [] }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

### OpenAPI Generation from Zod Schemas

```typescript
// src/lib/openapi.ts
import { z } from 'zod';
import { generateSchema } from '@anatine/zod-openapi';
import { CreateUserBodySchema, PaginationQuerySchema } from '../schemas/user';

export function generateOpenApiSpec() {
  return {
    openapi: '3.1.0',
    info: { title: 'Orchords API', version: '1.0.0' },
    paths: {
      '/users': {
        post: {
          summary: 'Create a user',
          requestBody: {
            required: true,
            content: {
              'application/json': {
                schema: generateSchema(CreateUserBodySchema),
              },
            },
          },
          responses: {
            '201': { description: 'User created' },
            '422': { description: 'Validation error' },
          },
        },
        get: {
          summary: 'List users',
          parameters: Object.entries(PaginationQuerySchema.shape).map(([name, schema]) => ({
            name,
            in: 'query',
            schema: generateSchema(schema as z.ZodTypeAny),
          })),
          responses: { '200': { description: 'User list' } },
        },
      },
    },
  };
}
```

---

## Implementation Details

- **`.strict()` vs `.passthrough()`**: `.strict()` rejects unknown keys (returns an error). `.passthrough()` strips unknown keys silently. For security, prefer `.strict()` on write endpoints — any unexpected field signals a client bug or an attack.
- **`z.coerce`**: Query parameters are always strings. `z.coerce.number()` calls `Number()` on the string, which accepts `" 1 "` (trimmed) and `"1e3"` (scientific notation). If you need stricter integer parsing, pair with `.int()` and `.finite()`.
- **Validation performance**: Parsing a 10-field Zod schema takes ~50 µs in the Workers runtime. For high-throughput routes (>1000 RPS per isolate), this is negligible. File upload or large array schemas may add 1–2 ms.
- **Safe parse vs parse**: `safeParse()` never throws — always use it in request handlers. `parse()` throws a `ZodError`, which must be caught; unhandled throws in Workers return a 500.
- **Header validation**: `request.headers` is a `Headers` object. Use `Object.fromEntries(request.headers.entries())` to convert to a plain object for Zod. Note that header names are lowercased by the Headers API.

---

## Anti-patterns

- **Validating only on the client side** — client validation is UX; server validation is security.
- **Using `z.any()` or skipping validation** for "internal" endpoints — internal endpoints are frequent pivot points in SSRF and lateral movement attacks.
- **Not mapping Zod errors to a stable format** — raw Zod error objects expose internal schema details; always map to RFC 7807 before responding.
- **Forgetting `.strict()`** on write endpoints — without it, `body.role = 'admin'` gets ignored silently instead of rejected with an error that alerts to the attack.
- **Validating after side effects** — validate first, act second. Never read from a DB or send an email before schema validation passes.

---

## Gotchas

- `z.string().email()` uses a simple regex, not full RFC 5321 compliance. It will reject some valid edge-case emails (e.g. `user+tag@sub.domain.co`). Test your production email formats.
- `z.coerce.number()` converts `""` (empty string) to `0`, which may be a valid default. Add `.min(1)` or `.nonEmpty()` upstream if empty strings should be rejected.
- Zod v3 and v4 APIs differ significantly (v4 uses `z.object`, v4/mini uses different imports). Pin your version and check bundle size after upgrades.
- When running `generateSchema` for OpenAPI, optional fields with defaults (e.g. `z.number().default(1)`) may not generate `required: false` correctly in all adapters — test the generated spec.

---

## Verification

```bash
# 1. Valid payload — expect 201
curl -si -X POST https://api.example.com/users \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer eyJtest.token.here' \
  -d '{"email":"alice@example.com","name":"Alice","password":"SecurePass1!"}'

# 2. Injection of unlisted field — expect 422 with field error
curl -si -X POST https://api.example.com/users \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer eyJtest.token.here' \
  -d '{"email":"bob@example.com","name":"Bob","password":"SecurePass1!","role":"admin"}'

# 3. Invalid email — expect 422
curl -si -X POST https://api.example.com/users \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer eyJtest.token.here' \
  -d '{"email":"not-an-email","name":"Carol","password":"SecurePass1!"}'

# 4. Query param coercion — page should be number 2
curl -si 'https://api.example.com/users?page=2&pageSize=10' | jq .page

# 5. Bundle size check
npx wrangler deploy --dry-run 2>&1 | grep 'Total size'
```

---

## Related

- `documentation/categories/security/workers-cors-policy-management.md`
- `documentation/categories/security/jwt-validation-workers.md`
- RFC 7807 Problem Details: https://datatracker.ietf.org/doc/html/rfc7807

---

## Sources

- Zod documentation: https://zod.dev
- RFC 7807 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc7807
- zod-to-openapi: https://github.com/asteasolutions/zod-to-openapi
- OWASP Input Validation Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
