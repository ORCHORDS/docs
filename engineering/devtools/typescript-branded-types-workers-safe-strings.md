# TypeScript Branded Types for Workers: Safe String Patterns

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker handles multiple string identifiers that look identical
at runtime but must never be confused — user IDs, tenant slugs, API key hashes,
D1 row primary keys, KV namespace keys. Without type-level enforcement a
function expecting a `UserId` happily accepts a `TenantSlug`, silently
corrupting data or causing security bugs.

TypeScript's structural type system treats `type UserId = string` and
`type TenantSlug = string` as identical. Branded types add a phantom tag that
makes them nominally distinct at compile time with zero runtime cost.

---

## Context

A **branded type** (also called an opaque type or nominal type) is a type
intersection that adds a unique phantom property:

```typescript
type Brand<T, B extends string> = T & { readonly __brand: B };
```

The `__brand` property never exists at runtime — it is purely a compile-time
marker. The result is that `UserId` and `TenantSlug` are structurally different
from TypeScript's perspective even though both are `string` at runtime.

This pattern is especially valuable in Workers where:

- A single Worker function often handles multiple entity types in one file.
- Env bindings, D1 queries, KV lookups, and route parameters all produce plain
  `string` values that need careful typing.
- The lack of a dependency-injection framework makes it easy to pass wrong IDs
  to database queries.

---

## Core Brand Utility

```typescript
// src/types/brand.ts

/**
 * Create a branded (nominal) type. The brand is a compile-time phantom —
 * no runtime overhead, no extra bytes in the response.
 */
export type Brand<T, B extends string> = T & { readonly __brand: B };

/**
 * Extract the underlying primitive from a branded type.
 * Useful for serialisation or passing to third-party APIs that expect `string`.
 */
export type Unbrand<T> = T extends Brand<infer U, string> ? U : T;

/**
 * A constructor / parser function that narrows an unknown value into a
 * branded type, throwing if the value fails validation.
 */
export type Parser<T> = (raw: unknown) => T;
```

---

## Defining Workers Domain Brands

```typescript
// src/types/ids.ts
import { Brand } from "./brand";

// Cloudflare D1 row IDs (UUID v4)
export type UserId   = Brand<string, "UserId">;
export type TenantId = Brand<string, "TenantId">;
export type PostId   = Brand<string, "PostId">;

// KV namespace keys
export type KVKey    = Brand<string, "KVKey">;

// API tokens — must never be logged
export type ApiToken = <redacted-secret> "ApiToken">;

// URL path segments that have been validated / encoded
export type SafePath = Brand<string, "SafePath">;

// Validated email addresses
export type EmailAddress = Brand<string, "EmailAddress">;
```

---

## Smart Constructors (Parsers)

Branded types need **constructors** that validate and cast raw input. These are
the only places where a `string` is cast to a branded type:

```typescript
// src/types/parsers.ts
import {
  UserId, TenantId, PostId, KVKey, ApiToken, SafePath, EmailAddress
} from "./ids";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function assertString(raw: unknown, name: string): string {
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new TypeError(`Expected non-empty string for ${name}, got ${JSON.stringify(raw)}`);
  }
  return raw;
}

export function parseUserId(raw: unknown): UserId {
  const s = assertString(raw, "UserId");
  if (!UUID_RE.test(s)) throw new TypeError(`Invalid UserId: ${s}`);
  return s as UserId;
}

export function parseTenantId(raw: unknown): TenantId {
  const s = assertString(raw, "TenantId");
  if (!UUID_RE.test(s)) throw new TypeError(`Invalid TenantId: ${s}`);
  return s as TenantId;
}

export function parsePostId(raw: unknown): PostId {
  return assertString(raw, "PostId") as PostId;
}

export function parseKVKey(raw: unknown): KVKey {
  const s = assertString(raw, "KVKey");
  // KV keys: max 512 bytes, no null bytes
  if (s.length > 512 || s.includes("\0")) throw new TypeError(`Invalid KVKey: ${s}`);
  return s as KVKey;
}

export function parseApiToken(raw: unknown): ApiToken {
  const s = assertString(raw, "ApiToken");
  if (s.length < 32) throw new TypeError("ApiToken too short");
  return s as ApiToken;
}

export function parseSafePath(raw: unknown): SafePath {
  const s = assertString(raw, "SafePath");
  // Prevent path traversal
  if (s.includes("..") || s.includes("\0")) throw new TypeError(`Unsafe path: ${s}`);
  return encodeURIComponent(s) as SafePath;
}

export function parseEmailAddress(raw: unknown): EmailAddress {
  const s = assertString(raw, "EmailAddress").toLowerCase();
  if (!EMAIL_RE.test(s)) throw new TypeError(`Invalid email: ${s}`);
  return s as EmailAddress;
}
```

---

## Using Branded Types in Workers

```typescript
// src/services/user-service.ts
import type { Env } from "../env";
import { UserId, TenantId } from "../types/ids";
import { parseUserId, parseTenantId } from "../types/parsers";

interface User {
  id: UserId;
  tenantId: TenantId;
  email: string;
  name: string;
}

export async function getUser(
  env: Env,
  tenantId: TenantId,  // ← cannot accidentally pass a UserId here
  userId: UserId
): Promise<User | null> {
  const result = await env.DB.prepare(
    "SELECT * FROM users WHERE id = ?1 AND tenant_id = ?2"
  )
    .bind(userId, tenantId)  // safe: branded strings bind as regular strings
    .first<User>();

  return result ?? null;
}

export async function cacheUser(env: Env, user: User): Promise<void> {
  const key = `user:${user.tenantId}:${user.id}` as import("../types/ids").KVKey;
  await env.KV.put(key, JSON.stringify(user), { expirationTtl: 3600 });
}
```

```typescript
// src/worker.ts
import { parseUserId, parseTenantId } from "./types/parsers";
import { getUser } from "./services/user-service";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Parse from route params — the cast happens once here, at the boundary
    const tenantId = parseTenantId(url.searchParams.get("tenantId"));
    const userId   = parseUserId(url.searchParams.get("userId"));

    const user = await getUser(env, tenantId, userId);
    if (!user) return new Response("Not Found", { status: 404 });

    return Response.json(user);
  },
} satisfies ExportedHandler<Env>;
```

---

## Result-Based Parsing (No-throw Alternative)

For HTTP handlers where a bad input should return 400 rather than throw:

```typescript
// src/types/result.ts
export type Ok<T>  = { ok: true;  value: T };
export type Err<E> = { ok: false; error: E };
export type Result<T, E = string> = Ok<T> | Err<E>;

export const ok  = <T>(value: T): Ok<T>   => ({ ok: true,  value });
export const err = <E>(error: E): Err<E>  => ({ ok: false, error });
```

```typescript
// src/types/safe-parsers.ts
import { UserId } from "./ids";
import { Result, ok, err } from "./result";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function safeParseUserId(raw: unknown): Result<UserId> {
  if (typeof raw !== "string" || !UUID_RE.test(raw)) {
    return err(`Invalid UserId: ${JSON.stringify(raw)}`);
  }
  return ok(raw as UserId);
}
```

```typescript
// src/worker.ts (safe-parse variant)
const userIdResult = safeParseUserId(url.searchParams.get("userId"));
if (!userIdResult.ok) {
  return new Response(userIdResult.error, { status: 400 });
}
const userId = userIdResult.value; // UserId — fully typed
```

---

## Preventing ApiToken Leaks

Mark sensitive brands so linters and code review notice them:

```typescript
// src/types/ids.ts (excerpt)
/**
 * @sensitive — never log, never serialize into response bodies
 */
export type ApiToken = <redacted-secret> "ApiToken">;
```

Pair with the ESLint `no-raw-env-log` custom rule from
`oxlint-custom-rule-workers-security.md` to catch accidental logging.

---

## Testing Parsers and Branded Functions

```typescript
// src/types/__tests__/parsers.test.ts
import { describe, it, expect } from "vitest";
import { parseUserId, parseTenantId, parseEmailAddress } from "../parsers";

describe("parseUserId", () => {
  it("accepts a valid UUID v4", () => {
    const id = parseUserId("550e8400-e29b-41d4-a716-446655440000");
    expect(typeof id).toBe("string");
  });

  it("rejects a non-UUID string", () => {
    expect(() => parseUserId("not-a-uuid")).toThrow(TypeError);
  });

  it("rejects null", () => {
    expect(() => parseUserId(null)).toThrow(TypeError);
  });
});

describe("parseEmailAddress", () => {
  it("normalises to lowercase", () => {
    expect(parseEmailAddress("Ada@EXAMPLE.COM")).toBe("ada@example.com");
  });

  it("rejects strings without @", () => {
    expect(() => parseEmailAddress("notanemail")).toThrow(TypeError);
  });
});
```

---

## Anti-patterns

- **Using `as UserId` directly in handler code.** The cast should live only in
  parser functions. Spreading it throughout the codebase defeats the purpose.
- **Brands on complex objects rather than primitives.** Branded types shine for
  `string`, `number`, and `bigint`. For complex objects use `zod` or similar
  for runtime validation with inferred types.
- **Forgetting to strip brands before serialisation.** Branded strings
  serialise identically to plain strings (`JSON.stringify` ignores phantom
  properties), but be deliberate: document that the strip happens at the JSON
  boundary.
- **Using brands as a substitute for runtime validation.** A brand without a
  smart constructor that validates the value is just documentation. Always pair
  the type with a parser.

---

## Gotchas

- `type UserId = Brand<string, "UserId">` is erased at runtime. If you pass a
  `UserId` to a function expecting `string`, TypeScript allows it (branded types
  are subtypes of their base type). The restriction is one-directional:
  `string` is not assignable to `UserId`.
- D1's `.bind()` accepts `string | number | null | ArrayBuffer` — passing a
  branded string works because it IS a string at runtime.
- Avoid `__brand` in JSON responses. If you `JSON.stringify(user)` where
  `user.id` is `UserId`, the output is just `"uuid-string"` — no phantom
  property leaks. This is the correct behavior.

---

## Verification

```bash
# Type-check: expect error on wrong brand usage
cat > /tmp/brand-test.ts << 'EOF'
import { UserId, TenantId } from "./src/types/ids";
declare const uid: UserId;
const tid: TenantId = uid;  // should error: Type 'UserId' is not assignable to type 'TenantId'
EOF
pnpm tsc --noEmit --strict /tmp/brand-test.ts

# Run parser unit tests
pnpm vitest run src/types/__tests__/parsers.test.ts
```

---

## Related

- `typescript-satisfies-operator-workers-type-narrowing.md`
- `typescript-template-literal-types-workers-route-pattern.md`
- `typescript-workers-env-interface-module-augmentation.md`
- `typescript-strict-mode-guide.md`
- `oxlint-custom-rule-workers-security.md`

---

## Sources

- https://www.typescriptlang.org/docs/handbook/2/types-from-types.html
- https://egghead.io/blog/using-branded-types-in-typescript
- https://developers.cloudflare.com/d1/worker-api/d1-database/#binding
- https://developers.cloudflare.com/workers/runtime-apis/kv/#write-key-value-pairs
- https://gcanti.github.io/fp-ts/modules/string.ts.html (fp-ts branded string patterns)
