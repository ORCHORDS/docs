# API Contract Testing for Workers Endpoints Using Zod

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Cloudflare Workers expose REST endpoints, and consumers (mobile apps, other services) depend on stable response shapes. Schema drift between what the Worker returns and what the consumer expects causes silent runtime failures that only surface in production. You need automated contract tests that catch breaking schema changes before they reach users.

---

## Context
Zod provides a TypeScript-first schema library that doubles as a runtime validator and a source of truth for both tests and documentation. By defining request and response schemas once as Zod objects, you get inferred TypeScript types, runtime parsing in tests via `schema.parse()`, and the ability to generate OpenAPI specs from the same definitions. `SELF.fetch()` in Vitest's Workers runtime lets you call your Worker handler directly in-process, giving you fast, hermetic contract tests. A CI check that compares the current Zod schema against a locked baseline prevents accidental consumer-breaking changes.

---

## Schema Definitions

```typescript
// src/schemas/user.ts
import { z } from 'zod';

export const CreateUserRequestSchema = z.object({
  name: z.string().min(1).max(100),
  email: z.string().email(),
  role: z.enum(['admin', 'editor', 'viewer']),
});

export const UserResponseSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  email: z.string().email(),
  role: z.enum(['admin', 'editor', 'viewer']),
  createdAt: z.string().datetime(),
});

export const ErrorResponseSchema = z.object({
  error: z.string(),
  code: z.number().int(),
});

export const UserListResponseSchema = z.object({
  users: z.array(UserResponseSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  pageSize: z.number().int().positive(),
});

// Export inferred types for use in fixtures and handlers
export type CreateUserRequest = z.infer<typeof CreateUserRequestSchema>;
export type UserResponse = z.infer<typeof UserResponseSchema>;
export type UserListResponse = z.infer<typeof UserListResponseSchema>;
```

---

## Implementation — Typed Test Fixtures

```typescript
// test/fixtures/users.ts
import type { CreateUserRequest, UserResponse } from '../../src/schemas/user';

// z.infer<> ensures fixture types stay in sync with schema automatically
export const validCreateUserPayload: CreateUserRequest = {
  name: 'Alice Nguyen',
  email: 'alice@example.com',
  role: 'editor',
};

export const invalidCreateUserPayloads: Array<Partial<CreateUserRequest>> = [
  { name: '', email: 'alice@example.com', role: 'editor' },   // empty name
  { name: 'Alice', email: 'not-an-email', role: 'editor' },   // bad email
  { name: 'Alice', email: 'alice@example.com', role: 'superuser' as any }, // invalid role
];

export const seedUser: UserResponse = {
  id: '00000000-0000-0000-0000-000000000001',
  name: 'Alice Nguyen',
  email: 'alice@example.com',
  role: 'editor',
  createdAt: '2026-08-24T00:00:00.000Z',
};
```

---

## Contract Tests with SELF.fetch()

```typescript
// test/contract/users.contract.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';
import {
  UserResponseSchema,
  UserListResponseSchema,
  ErrorResponseSchema,
  CreateUserRequestSchema,
} from '../../src/schemas/user';
import { validCreateUserPayload, invalidCreateUserPayloads, seedUser } from '../fixtures/users';

declare module 'cloudflare:test' {
  interface ProvidedEnv extends Env {}
}

beforeAll(async () => {
  // Seed D1 with deterministic test data
  await env.DB.prepare(
    `INSERT OR REPLACE INTO users (id, name, email, role, created_at) VALUES (?, ?, ?, ?, ?)`
  ).bind(
    seedUser.id,
    seedUser.name,
    seedUser.email,
    seedUser.role,
    seedUser.createdAt,
  ).run();
});

describe('GET /api/users — contract', () => {
  it('response conforms to UserListResponseSchema', async () => {
    const res = await SELF.fetch('http://localhost/api/users');
    expect(res.status).toBe(200);
    const body = await res.json();
    // parse() throws ZodError with full diff on mismatch — clear failure messages
    const parsed = UserListResponseSchema.parse(body);
    expect(parsed.total).toBeGreaterThanOrEqual(1);
  });

  it('individual user items match UserResponseSchema', async () => {
    const res = await SELF.fetch('http://localhost/api/users');
    const { users } = UserListResponseSchema.parse(await res.json());
    for (const user of users) {
      UserResponseSchema.parse(user); // throws on first violation
    }
  });
});

describe('POST /api/users — contract', () => {
  it('valid payload returns 201 with UserResponseSchema body', async () => {
    const res = await SELF.fetch('http://localhost/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(validCreateUserPayload),
    });
    expect(res.status).toBe(201);
    UserResponseSchema.parse(await res.json());
  });

  it.each(invalidCreateUserPayloads)(
    'invalid payload %# returns 400 with ErrorResponseSchema body',
    async (payload) => {
      const res = await SELF.fetch('http://localhost/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      expect(res.status).toBe(400);
      ErrorResponseSchema.parse(await res.json());
    },
  );
});

describe('GET /api/users/:id — contract', () => {
  it('known id returns UserResponseSchema', async () => {
    const res = await SELF.fetch(`http://localhost/api/users/${seedUser.id}`);
    expect(res.status).toBe(200);
    const parsed = UserResponseSchema.parse(await res.json());
    expect(parsed.id).toBe(seedUser.id);
  });

  it('unknown id returns 404 with ErrorResponseSchema', async () => {
    const res = await SELF.fetch('http://localhost/api/users/does-not-exist');
    expect(res.status).toBe(404);
    ErrorResponseSchema.parse(await res.json());
  });
});
```

---

## OpenAPI Generation from Same Zod Schemas

```typescript
// scripts/generate-openapi.ts
import { generateSchema } from '@anatine/zod-openapi';
import {
  CreateUserRequestSchema,
  UserResponseSchema,
  UserListResponseSchema,
  ErrorResponseSchema,
} from '../src/schemas/user';
import { writeFileSync } from 'fs';

const spec = {
  openapi: '3.1.0',
  info: { title: 'Users API', version: '1.0.0' },
  paths: {
    '/api/users': {
      get: {
        summary: 'List users',
        responses: {
          '200': {
            description: 'OK',
            content: { 'application/json': { schema: generateSchema(UserListResponseSchema) } },
          },
        },
      },
      post: {
        summary: 'Create user',
        requestBody: {
          required: true,
          content: { 'application/json': { schema: generateSchema(CreateUserRequestSchema) } },
        },
        responses: {
          '201': {
            description: 'Created',
            content: { 'application/json': { schema: generateSchema(UserResponseSchema) } },
          },
          '400': {
            description: 'Bad Request',
            content: { 'application/json': { schema: generateSchema(ErrorResponseSchema) } },
          },
        },
      },
    },
  },
};

writeFileSync('openapi.json', JSON.stringify(spec, null, 2));
console.log('OpenAPI spec written to openapi.json');
```

---

## Anti-patterns
- **Separate schema definitions for tests and source** — Any divergence between the types used in your handler and the types used in your tests means the contract test isn't testing the real contract. Always import from a single shared schema file.
- **Using `safeParse` without asserting `success`** — `safeParse` silently skips validation errors if you only access `.data`. Use `parse()` in tests so failures are thrown immediately with a full ZodError diff.
- **Asserting only on status codes** — A 200 with the wrong body shape is a broken contract. Always parse the body through the Zod schema after checking the status.
- **Forgetting to version schemas** — When you evolve schemas, keep the old version accessible so CI can compare against locked consumer expectations.

---

## Gotchas
- `z.string().datetime()` requires a full ISO-8601 string with timezone offset. `new Date().toISOString()` produces the `Z`-suffix format which satisfies this, but `date.toLocaleDateString()` does not.
- ZodError messages in Vitest show as a long string. Add `import { fromZodError } from 'zod-validation-error'` and wrap `parse()` calls in try/catch to get human-readable error messages in test output.
- `SELF.fetch()` requires the `cloudflare:test` environment. Ensure `vitest.config.ts` sets `environment: 'cloudflare:workers'` and your `wrangler.toml` has the D1 binding declared under `[env.test]`.
- Generating OpenAPI from Zod requires `@anatine/zod-openapi` or `zod-to-json-schema`. Neither is the official Zod package — pin versions carefully to avoid schema generation drift.

---

## Verification

```bash
# Run contract tests only
npx vitest run test/contract --reporter=verbose

# Generate and diff the OpenAPI spec
npx ts-node scripts/generate-openapi.ts
git diff openapi.json  # should be empty if no schema changed

# Type-check schema inferences
npx tsc --noEmit

# Full CI check: tests + schema diff
npx vitest run test/contract && npx ts-node scripts/generate-openapi.ts && git diff --exit-code openapi.json
```

---

## Related
- `workers-golden-file-testing-api-responses.md`
- `workers-test-coverage-c8-vitest.md`
- `workers-property-based-testing-fast-check.md`

---

## Sources
- Zod documentation — https://zod.dev
- Vitest Cloudflare Workers environment — https://vitest.dev/guide/environment
- @anatine/zod-openapi — https://github.com/anatine/zod-plugins/tree/main/packages/zod-openapi
- Cloudflare Workers Testing — https://developers.cloudflare.com/workers/testing/vitest-integration/
