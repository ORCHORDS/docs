# Backward Compatibility Testing for Versioned Worker APIs

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You maintain `/v1/` and `/v2/` endpoints in the same Worker. A refactor that fixes a bug in v2 silently breaks a v1 contract that clients still depend on. You need a shared test suite that runs identical assertions against both versions, plus targeted tests that capture intentional divergence.

## Context

Cloudflare Workers route versioning is typically done via URL prefix (`/v1/`, `/v2/`) or a custom header (`API-Version: 2`). The Worker dispatches internally. The test strategy parametrises the base URL so the same spec file exercises both versions in one Vitest run, using `@cloudflare/vitest-pool-workers` with a real Miniflare environment.

---

## Section 1 — Shared test factory pattern

```ts
// tests/api/shared-contract.ts
import { type SELF } from 'cloudflare:test';

export type ApiVersion = 'v1' | 'v2';

export interface VersionedSuite {
  version: ApiVersion;
  worker: typeof SELF;
}

/**
 * buildUrl constructs a versioned URL for the given path.
 */
export function buildUrl(version: ApiVersion, path: string): string {
  return `https://api.example.com/${version}${path}`;
}

/**
 * sharedContractSuite runs the same assertions for any API version.
 * Call it once per version inside a describe block.
 */
export function sharedContractSuite({ version, worker }: VersionedSuite) {
  describe(`${version} — shared contract`, () => {
    it('GET /users/:id returns 200 with expected shape', async () => {
      const res = await worker.fetch(buildUrl(version, '/users/1'));
      expect(res.status).toBe(200);

      const body = await res.json<Record<string, unknown>>();
      // Fields that MUST exist in every version
      expect(body).toHaveProperty('id');
      expect(body).toHaveProperty('email');
      expect(typeof body.id).toBe('number');
      expect(typeof body.email).toBe('string');
    });

    it('POST /users with invalid payload returns 422', async () => {
      const res = await worker.fetch(buildUrl(version, '/users'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'not-an-email' }),
      });
      expect(res.status).toBe(422);
    });

    it('unknown route returns 404', async () => {
      const res = await worker.fetch(buildUrl(version, '/does-not-exist'));
      expect(res.status).toBe(404);
    });

    it('responds within 50 ms (cold start excluded)', async () => {
      const start = Date.now();
      await worker.fetch(buildUrl(version, '/users/1'));
      expect(Date.now() - start).toBeLessThan(50);
    });
  });
}
```

## Section 2 — Per-version test files

```ts
// tests/api/v1.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';
import { sharedContractSuite } from './shared-contract';

describe('API v1', () => {
  // Seed DB for v1 tests
  beforeAll(async () => {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO users (id, email) VALUES (1, 'alice@example.com')`
    ).run();
  });

  // Run all shared assertions
  sharedContractSuite({ version: 'v1', worker: SELF });

  // v1-specific: snake_case field name (deprecated in v2)
  it('GET /users/:id includes legacy snake_case field', async () => {
    const res = await SELF.fetch('https://api.example.com/v1/users/1');
    const body = await res.json<Record<string, unknown>>();
    expect(body).toHaveProperty('created_at'); // deprecated in v2
  });
});
```

```ts
// tests/api/v2.test.ts
import { env, SELF } from 'cloudflare:test';
import { describe, it, expect, beforeAll } from 'vitest';
import { sharedContractSuite } from './shared-contract';

describe('API v2', () => {
  beforeAll(async () => {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO users (id, email, display_name) VALUES (1, 'alice@example.com', 'Alice')`
    ).run();
  });

  sharedContractSuite({ version: 'v2', worker: SELF });

  // v2-specific: camelCase replaces snake_case
  it('GET /users/:id returns camelCase createdAt instead of created_at', async () => {
    const res = await SELF.fetch('https://api.example.com/v2/users/1');
    const body = await res.json<Record<string, unknown>>();
    expect(body).toHaveProperty('createdAt');
    expect(body).not.toHaveProperty('created_at');
  });

  // v2-specific: new field
  it('GET /users/:id includes displayName', async () => {
    const res = await SELF.fetch('https://api.example.com/v2/users/1');
    const body = await res.json<Record<string, unknown>>();
    expect(body).toHaveProperty('displayName', 'Alice');
  });
});
```

## Section 3 — Schema diff detection with Zod

```ts
// tests/api/schema-diff.test.ts
import { SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';
import { z } from 'zod';

// V1 schema — acts as the contract snapshot
const UserV1 = z.object({
  id: z.number(),
  email: z.string().email(),
  created_at: z.string().datetime(),
});

// V2 schema — intentionally different
const UserV2 = z.object({
  id: z.number(),
  email: z.string().email(),
  displayName: z.string(),
  createdAt: z.string().datetime(),
});

describe('Schema contract', () => {
  it('v1 /users/:id response matches UserV1 schema', async () => {
    const res = await SELF.fetch('https://api.example.com/v1/users/1');
    const body = await res.json();
    const result = UserV1.safeParse(body);
    expect(result.success, JSON.stringify(result.error?.issues)).toBe(true);
  });

  it('v2 /users/:id response matches UserV2 schema', async () => {
    const res = await SELF.fetch('https://api.example.com/v2/users/1');
    const body = await res.json();
    const result = UserV2.safeParse(body);
    expect(result.success, JSON.stringify(result.error?.issues)).toBe(true);
  });

  it('v1 response does NOT contain v2-only fields (no leakage)', async () => {
    const res = await SELF.fetch('https://api.example.com/v1/users/1');
    const body = await res.json<Record<string, unknown>>();
    expect(body).not.toHaveProperty('displayName');
    expect(body).not.toHaveProperty('createdAt');
  });
});
```

## Section 4 — Deprecation warning header assertions

```ts
// tests/api/deprecation-headers.test.ts
import { SELF } from 'cloudflare:test';
import { describe, it, expect } from 'vitest';

describe('Deprecation headers', () => {
  it('v1 endpoints return Deprecation header per RFC 8594', async () => {
    const res = await SELF.fetch('https://api.example.com/v1/users/1');
    // RFC 8594 deprecation date
    expect(res.headers.get('Deprecation')).toMatch(
      /^@?\d{4}-\d{2}-\d{2}|true$/
    );
  });

  it('v1 endpoints return Sunset header', async () => {
    const res = await SELF.fetch('https://api.example.com/v1/users/1');
    const sunset = res.headers.get('Sunset');
    expect(sunset).not.toBeNull();
    // Sunset must be a future date
    expect(new Date(sunset!).getTime()).toBeGreaterThan(Date.now());
  });

  it('v1 endpoints return Link header pointing to v2 docs', async () => {
    const res = await SELF.fetch('https://api.example.com/v1/users/1');
    const link = res.headers.get('Link');
    expect(link).toContain('rel="successor-version"');
    expect(link).toContain('/v2/');
  });

  it('v2 endpoints do NOT return Deprecation header', async () => {
    const res = await SELF.fetch('https://api.example.com/v2/users/1');
    expect(res.headers.get('Deprecation')).toBeNull();
  });
});
```

## Anti-patterns

- **Copy-pasting test files per version** — maintenance nightmare. Use the shared factory as shown above.
- **Testing only the happy path on both versions** — deprecation and schema drift bugs live in error paths. Include 4xx scenarios in the shared contract.
- **Hardcoding version strings in test URLs** — parameterise via `buildUrl()` so renaming a version updates every test.

## Gotchas

- Zod schema tests catch shape regressions but not semantic regressions (e.g., `email` field returning the user ID). Combine with value assertions.
- The `Sunset` header value must survive Worker deploys — store it in a Worker environment variable, not as a code constant, to avoid drift.
- `beforeAll` seeds run once per describe block, not once per test file. Use `beforeEach` with `DELETE FROM` for tests that mutate state.

## Verification

```bash
# Run all API version tests
npx vitest run tests/api/

# Run only the schema-diff suite
npx vitest run tests/api/schema-diff.test.ts

# Confirm both v1 and v2 test files are picked up
npx vitest list tests/api/
```

## Related

- `documentation/categories/testing/workers-d1-migration-rollback-test.md`
- `documentation/routing/workers-url-versioning-patterns.md`
- `documentation/categories/testing/workers-chaos-fault-injection-vitest.md`

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://datatracker.ietf.org/doc/html/rfc8594
- https://zod.dev/
