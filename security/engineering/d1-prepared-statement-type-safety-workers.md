# D1 Prepared Statement Parameter Type Safety Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker binds parameters to a D1 prepared statement using `.bind(...)` but:

- A `number | undefined` is accidentally bound as `undefined`, which D1 treats as `NULL`,
  silently corrupting rows or bypassing `WHERE` conditions.
- A string field that should be an integer is passed through from user input without
  coercion, and SQLite's implicit type affinity silently converts it — or doesn't.
- A boolean is bound as JavaScript `true`/`false`; D1/SQLite stores it as `1`/`0` but
  the application reads it back expecting the original type and compares incorrectly.
- A UUID comes in as mixed-case from one client and lowercase from another; uniqueness
  constraints pass, but lookups fail.

These bugs do not produce SQL injection but they produce **data integrity failures** and
**logic bypass vulnerabilities** that are equally dangerous.

---

## Context

D1 exposes a SQLite-compatible database via the `D1Database` binding. Parameters are
bound positionally with `?` placeholders:

```typescript
const stmt = env.DB.prepare('SELECT * FROM users WHERE id = ?').bind(userId);
```

D1's `.bind()` accepts `string | number | boolean | null | ArrayBuffer | ArrayBufferView`.
SQLite has five storage classes: NULL, INTEGER, REAL, TEXT, BLOB. The mapping between
JavaScript types and SQLite storage classes is mostly predictable but has sharp edges.

---

## Type Mapping Reference

| JavaScript value | SQLite storage class | Gotcha |
|---|---|---|
| `null` | NULL | — |
| `undefined` | NULL | **Silent!** D1 converts `undefined` to NULL without error |
| `true` / `false` | INTEGER (1 / 0) | Read back via `row.active` returns `1` or `0`, not `true`/`false` |
| `42` (integer) | INTEGER | — |
| `3.14` (float) | REAL | — |
| `"hello"` | TEXT | — |
| `Uint8Array` / `ArrayBuffer` | BLOB | — |
| `NaN` | **throws** at bind time in Workers runtime | Cannot bind NaN |
| `Infinity` | **throws** at bind time in Workers runtime | Cannot bind Infinity |
| `BigInt` | **throws** — not accepted | Integers must fit in `Number` safely |

---

## Defensive Binding Utility

Build a typed binding helper that validates before it reaches D1:

```typescript
// src/db/bind.ts

export type D1BindValue = string | number | boolean | null | ArrayBuffer | Uint8Array;

export class BindError extends Error {
  constructor(
    public readonly param: string,
    public readonly value: unknown,
    message: string,
  ) {
    super(`Bind error for param "${param}": ${message} (got ${typeof value} ${String(value)})`);
    this.name = 'BindError';
  }
}

export function bindString(param: string, value: unknown): string {
  if (typeof value !== 'string') throw new BindError(param, value, 'expected string');
  return value;
}

export function bindInt(param: string, value: unknown): number {
  const n = Number(value);
  if (!Number.isInteger(n) || !Number.isFinite(n)) {
    throw new BindError(param, value, 'expected integer');
  }
  return n;
}

export function bindPositiveInt(param: string, value: unknown): number {
  const n = bindInt(param, value);
  if (n <= 0) throw new BindError(param, value, 'expected positive integer');
  return n;
}

export function bindFloat(param: string, value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) throw new BindError(param, value, 'expected finite number');
  return n;
}

export function bindUuid(param: string, value: unknown): string {
  if (typeof value !== 'string') throw new BindError(param, value, 'expected string UUID');
  const lower = value.toLowerCase();
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  if (!UUID_RE.test(lower)) throw new BindError(param, value, 'invalid UUID format');
  return lower; // normalise to lowercase
}

export function bindBoolean(param: string, value: unknown): number {
  // Store as INTEGER 1/0 to avoid read-back type confusion
  if (typeof value !== 'boolean') throw new BindError(param, value, 'expected boolean');
  return value ? 1 : 0;
}

export function bindNullable<T extends D1BindValue>(
  param: string,
  value: unknown,
  innerBind: (p: string, v: unknown) => T,
): T | null {
  if (value === null || value === undefined) return null;
  return innerBind(param, value);
}
```

---

## Applying the Helpers to Real Queries

```typescript
// src/db/users.ts
import { bindUuid, bindString, bindBoolean, bindNullable, bindInt } from './bind';

interface Env {
  DB: D1Database;
}

export interface CreateUserInput {
  id: string;
  email: string;
  displayName: string;
  isAdmin: boolean;
  referrerId?: string | null;
}

export async function createUser(env: Env, input: CreateUserInput): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO users (id, email, display_name, is_admin, referrer_id)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(
      bindUuid('id', input.id),
      bindString('email', input.email),
      bindString('displayName', input.displayName),
      bindBoolean('isAdmin', input.isAdmin),
      bindNullable('referrerId', input.referrerId, bindUuid),
    )
    .run();
}

export async function getUserById(env: Env, id: string) {
  return env.DB.prepare('SELECT * FROM users WHERE id = ?')
    .bind(bindUuid('id', id))
    .first<{ id: string; email: string; display_name: string; is_admin: number }>();
}

// Type-safe boolean read-back
export function userIsAdmin(row: { is_admin: number }): boolean {
  return row.is_admin === 1;
}
```

---

## Handling `undefined` from Request Bodies

A common source of `undefined` bindings is destructuring JSON bodies without defaults:

```typescript
// DANGEROUS — role may be undefined if the client omits the field
const { userId, role } = await request.json<{ userId: string; role?: string }>();
await env.DB.prepare('INSERT INTO memberships (user_id, role) VALUES (?, ?)')
  .bind(userId, role)   // role is undefined → stored as NULL
  .run();

// SAFE — reject explicitly or provide a default
const body = await request.json<unknown>();
const userId = bindUuid('userId', (body as any).userId);
const role = bindString('role', (body as any).role ?? 'member');
```

---

## Numeric Overflow and Large IDs

SQLite's INTEGER stores up to 8-byte signed integers (max 9,223,372,036,854,775,807).
JavaScript's `Number` type loses precision above `Number.MAX_SAFE_INTEGER` (2^53 − 1).
If your schema uses auto-increment IDs that could grow large, use TEXT-typed UUIDs or
string-encoded IDs instead of JavaScript numbers.

```typescript
// DANGEROUS for IDs approaching 2^53
const id = bindInt('id', request.params.id); // precision loss possible

// SAFE — use UUID primary keys
const id = bindUuid('id', request.params.id);
```

---

## Schema Validation with Zod Before Binding

Pair the binding utilities with Zod for request validation so type errors are caught at
the boundary, not inside the DB call:

```typescript
// src/routes/users.ts
import { z } from 'zod';
import { createUser } from '../db/users';

const CreateUserSchema = z.object({
  id: z.string().uuid().toLowerCase(),
  email: z.string().email().max(254),
  displayName: z.string().min(1).max(100),
  isAdmin: z.boolean(),
  referrerId: z.string().uuid().toLowerCase().nullable().optional(),
});

export const onRequestPost: PagesFunction<Env> = async (context) => {
  const body = await context.request.json<unknown>();
  const parsed = CreateUserSchema.safeParse(body);

  if (!parsed.success) {
    return Response.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  await createUser(context.env, parsed.data);
  return Response.json({ ok: true }, { status: 201 });
};
```

---

## Anti-patterns

- **Binding values directly from `request.json()` without validation.** User input is
  always untrusted; its types are not guaranteed by the runtime.
- **Using string template literals to build SQL.** Even with sanitisation, this defeats
  the purpose of prepared statements.
- **Reading boolean columns as JavaScript `boolean`.** D1 returns `0`/`1` for INTEGER
  columns; comparing with `=== true` will always be false.
- **Storing UUIDs in mixed case.** Case-insensitive uniqueness constraints still allow
  duplicate lookups if the application uses inconsistent casing.
- **Binding an entire object with `JSON.stringify` into a single parameter.** This stores
  unindexed JSON blobs, bypassing SQLite's type system and making queries impossible
  without JSON function operators.

---

## Gotchas

- `D1PreparedStatement.bind()` does **not** throw on `undefined` — it silently casts to
  NULL. This is the single most common source of accidental NULL writes.
- `D1Result.results` returns rows as plain objects with column names as keys. There is no
  automatic TypeScript type mapping — add explicit type parameters:
  `stmt.all<MyRow>()`.
- Boolean columns stored as INTEGER `0`/`1` are returned as `number` in TypeScript.
  There is no automatic coercion to `boolean`.
- Very long strings bound to TEXT columns succeed in D1 but may violate application-level
  constraints (e.g., max email length). Validate before binding.
- Floating-point numbers bound as REAL lose precision for values that cannot be
  represented exactly in IEEE 754 binary64.

---

## Verification

```typescript
// tests/bind.test.ts
import { bindUuid, bindInt, BindError } from '../src/db/bind';

describe('bindUuid', () => {
  it('accepts lowercase UUID', () => {
    expect(bindUuid('id', '123e4567-e89b-12d3-a456-426614174000'))
      .toBe('123e4567-e89b-12d3-a456-426614174000');
  });
  it('normalises uppercase to lowercase', () => {
    expect(bindUuid('id', '123E4567-E89B-12D3-A456-426614174000'))
      .toBe('123e4567-e89b-12d3-a456-426614174000');
  });
  it('throws on non-UUID string', () => {
    expect(() => bindUuid('id', 'not-a-uuid')).toThrow(BindError);
  });
  it('throws on undefined', () => {
    expect(() => bindUuid('id', undefined)).toThrow(BindError);
  });
});

describe('bindInt', () => {
  it('rejects floating-point', () => {
    expect(() => bindInt('count', 3.14)).toThrow(BindError);
  });
  it('rejects NaN', () => {
    expect(() => bindInt('count', NaN)).toThrow(BindError);
  });
});
```

---

## Related

- `sql-injection-prevention-d1-workers.md`
- `d1-row-level-security-tenant-isolation.md`
- `d1-json-column-injection-prevention.md`
- `api-schema-validation-openapi-zod-workers.md`
- `d1-atomic-transactions-toctou-prevention.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- SQLite data types — https://www.sqlite.org/datatype3.html
- Zod schema validation — https://zod.dev
- OWASP Input Validation Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
