# `crypto.randomUUID is not a function` on Older Compatibility Dates in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker calls `crypto.randomUUID()` to generate a request ID or a correlation token. The Worker throws `TypeError: crypto.randomUUID is not a function` at runtime, or the TypeScript compiler errors with `Property 'randomUUID' does not exist on type 'Crypto'`. The issue only occurs on Workers that have an older `compatibility_date` set in `wrangler.toml`.

---

## Context

Cloudflare Workers exposes the Web Crypto API via the global `crypto` object. The `randomUUID()` method was added to the Web Crypto spec and subsequently to the Workers runtime, but it is only enabled for Workers whose `compatibility_date` is `2022-07-21` or later. Workers with an earlier date see the `crypto` object without `randomUUID`, even if the underlying runtime version supports it. The compatibility date system is Cloudflare's mechanism for opt-in breaking changes; setting it too conservatively locks out newer APIs. This error frequently appears when cloning or upgrading an older project without updating `wrangler.toml`.

---

## What Went Wrong

```toml
# wrangler.toml — compatibility date too old
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2021-11-01"   # ← predates randomUUID support
```

```typescript
// src/index.ts
export default {
  async fetch(request: Request): Promise<Response> {
    // Throws: TypeError: crypto.randomUUID is not a function
    const requestId = crypto.randomUUID();

    return new Response(`Request ID: ${requestId}`);
  },
};
```

## Root Cause

`crypto.randomUUID()` was introduced into the Workers runtime behind the compatibility flag `web_crypto_random_uuid`, which is automatically enabled for `compatibility_date >= 2022-07-21`. Workers with an older date do not have this flag active, so `crypto.randomUUID` is `undefined`, causing the `TypeError` when called.

Reference: [https://developers.cloudflare.com/workers/configuration/compatibility-dates/#web-crypto-random-uuid](https://developers.cloudflare.com/workers/configuration/compatibility-dates/#web-crypto-random-uuid)

## The Fix

### Option 1 — Update compatibility date (preferred)

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2022-07-21"   # minimum date for randomUUID
# Bumping further is safe — review the changelog for any breaking changes
# between your old date and the new one before deploying to production.
```

No code changes required; `crypto.randomUUID()` becomes available immediately.

### Option 2 — Polyfill with `crypto.getRandomValues()` (zero-dependency, any compat date)

```typescript
// src/utils/uuid.ts

/**
 * Generates a RFC-4122 version 4 UUID.
 * Uses the Web Crypto API's getRandomValues(), available on all compat dates.
 * Falls back to the native randomUUID() when available for better performance.
 */
export function randomUUIDv4(): string {
  if (typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  // Manual UUID v4 via getRandomValues
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);

  // Set version (4) and variant (RFC 4122) bits
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));

  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}
```

Usage:

```typescript
// src/index.ts — fixed
import { randomUUIDv4 } from './utils/uuid';

export default {
  async fetch(request: Request): Promise<Response> {
    const requestId = randomUUIDv4(); // works on any compatibility date

    return new Response(`Request ID: ${requestId}`, {
      headers: { 'X-Request-Id': requestId },
    });
  },
};
```

## Verification

```bash
# 1. Check which compatibility date is active
cat wrangler.toml | grep compatibility_date

# 2. Run locally
wrangler dev

# 3. Smoke test
curl http://localhost:8787/
# Expected: "Request ID: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"

# 4. Validate UUID format
curl -s http://localhost:8787/ | grep -Eo '[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}'

# 5. Unit test the polyfill
npx vitest run src/utils/uuid.test.ts
```

Unit test:

```typescript
// src/utils/uuid.test.ts
import { describe, it, expect } from 'vitest';
import { randomUUIDv4 } from './uuid';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe('randomUUIDv4', () => {
  it('returns a valid v4 UUID', () => {
    expect(randomUUIDv4()).toMatch(UUID_RE);
  });

  it('returns unique values', () => {
    const ids = new Set(Array.from({ length: 1000 }, () => randomUUIDv4()));
    expect(ids.size).toBe(1000);
  });
});
```

---

## Anti-patterns

- **Using `Math.random()` as a UUID source** — Not cryptographically secure; produces predictable values that should never be used as identifiers in security-sensitive contexts (session tokens, correlation IDs).
- **Importing the `uuid` npm package unnecessarily** — The Workers runtime provides `crypto.getRandomValues()` natively; there is no reason to add a third-party dependency when the above polyfill is four lines.
- **Pinning `compatibility_date` to the project start date indefinitely** — The date should be reviewed and bumped periodically; leaving it stale means missing runtime security patches and new APIs.

---

## Gotchas

- TypeScript types: `@cloudflare/workers-types` versions before `4.x` may not include the `randomUUID` signature on `Crypto`. Update the package or add a local declaration: `declare function randomUUID(): string;` inside the `Crypto` interface.
- `compatibility_date` in `wrangler.toml` only gates *Workers runtime* behaviour. The TypeScript compiler checks types independently; even with the correct date, you may need to update `@cloudflare/workers-types` to suppress TS errors.
- When using `wrangler dev`, the locally-served Worker uses the `compatibility_date` from `wrangler.toml`, not the date of the deployed Worker on the dashboard. Ensure both are in sync.
- Bumping `compatibility_date` across multiple compatibility flags at once can introduce unintentional breaking changes. Review the [Cloudflare compatibility changelog](https://developers.cloudflare.com/workers/configuration/compatibility-dates/) for all flags activated between your old and new date.

---

## Related

- `workers-instanceof-error-cross-realm.md`
- `workers-fetch-body-already-consumed.md`

---

## Sources

- Cloudflare Workers Compatibility Dates — https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- Web Crypto API — randomUUID — https://developer.mozilla.org/en-US/docs/Web/API/Crypto/randomUUID
- RFC 4122 UUID specification — https://www.rfc-editor.org/rfc/rfc4122
