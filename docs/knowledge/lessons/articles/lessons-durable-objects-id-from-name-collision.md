# Durable Objects idFromName Collision — Data Bleed Between Features

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Two independent features — a shopping cart and a real-time inventory reservation system — both used `env.SESSION_DO.idFromName(userId)` to obtain a Durable Object ID. After the inventory feature shipped, carts began returning inventory reservation state mixed into cart responses. On investigation, both features were routing to the exact same Durable Object instance for each user, causing their state to share storage.

---

## Context

Cloudflare Durable Objects have a unique identity derived from their namespace (the Worker binding) and a name or raw ID. `env.DO_BINDING.idFromName(name)` is a deterministic hash: the same binding and the same name always produce the same 64-byte ID, which routes to the same single Durable Object instance in the world. If two different features share the same DO binding and independently call `idFromName(userId)`, they will both be directed to the same DO instance. Any state that instance stores is shared between them, even if the feature code treats it as isolated. This is not immediately obvious because the DO class code is the same file — the bug only manifests when state from one feature's storage keys leaks into another feature's reads.

---

## Root Cause

```typescript
// wrangler.toml — single binding used for two features
// [[durable_objects.bindings]]
// name = "SESSION_DO"
// class_name = "SessionDO"

// feature-cart/cart.ts — Feature A
export async function getCart(env: Env, userId: string): Promise<Cart> {
  // BAD: plain userId as the name
  const id = env.SESSION_DO.idFromName(userId);
  const stub = env.SESSION_DO.get(id);
  return stub.fetch(new Request('https://do/cart')).then(r => r.json<Cart>());
}

// feature-inventory/reservation.ts — Feature B
export async function getReservation(env: Env, userId: string): Promise<Reservation> {
  // BAD: same binding, same name → SAME DO instance as Feature A
  const id = env.SESSION_DO.idFromName(userId);
  const stub = env.SESSION_DO.get(id);
  return stub.fetch(new Request('https://do/reservation')).then(r => r.json<Reservation>());
}
```

Both `getCart` and `getReservation` call `env.SESSION_DO.idFromName(userId)` with an identical `userId` string. The resulting ID is identical. Both features contact the same running DO instance. Inside the DO, storage keys from cart operations (`cart:items`, `cart:coupon`) and reservation operations (`reservation:sku`, `reservation:expires`) coexist in the same storage namespace. If either feature iterates `storage.list()` or uses non-prefixed keys, data bleeds.

---

## Fix

### Option A — Namespace-prefix the name (lowest migration cost)

```typescript
// feature-cart/cart.ts
export async function getCart(env: Env, userId: string): Promise<Cart> {
  // GOOD: feature-scoped prefix prevents collision
  const id = env.SESSION_DO.idFromName(`cart:${userId}`);
  const stub = env.SESSION_DO.get(id);
  return stub.fetch(new Request('https://do/cart')).then(r => r.json<Cart>());
}

// feature-inventory/reservation.ts
export async function getReservation(env: Env, userId: string): Promise<Reservation> {
  // GOOD: different prefix → different DO instance
  const id = env.SESSION_DO.idFromName(`reservation:${userId}`);
  const stub = env.SESSION_DO.get(id);
  return stub.fetch(new Request('https://do/reservation')).then(r => r.json<Reservation>());
}
```

> Note: changing the name prefix creates a new DO instance. Existing state in the old (un-prefixed) instances is orphaned — plan a migration if that state must be preserved.

### Option B — Separate DO classes per feature (preferred for long-term isolation)

```toml
# wrangler.toml
[[durable_objects.bindings]]
name = "CART_DO"
class_name = "CartDO"

[[durable_objects.bindings]]
name = "RESERVATION_DO"
class_name = "ReservationDO"
```

```typescript
// feature-cart/cart.ts
export async function getCart(env: Env, userId: string): Promise<Cart> {
  const id = env.CART_DO.idFromName(userId);
  const stub = env.CART_DO.get(id);
  return stub.fetch(new Request('https://do/cart')).then(r => r.json<Cart>());
}

// feature-inventory/reservation.ts
export async function getReservation(env: Env, userId: string): Promise<Reservation> {
  const id = env.RESERVATION_DO.idFromName(userId);
  const stub = env.RESERVATION_DO.get(id);
  return stub.fetch(new Request('https://do/reservation')).then(r => r.json<Reservation>());
}

// worker/durable-objects/CartDO.ts
export class CartDO implements DurableObject {
  constructor(private readonly state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/cart') {
      const items = await this.state.storage.get<CartItem[]>('items') ?? [];
      return Response.json({ items });
    }
    return new Response('not found', { status: 404 });
  }
}

// worker/durable-objects/ReservationDO.ts
export class ReservationDO implements DurableObject {
  constructor(private readonly state: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === '/reservation') {
      const reservation = await this.state.storage.get<Reservation>('active');
      return Response.json(reservation ?? null);
    }
    return new Response('not found', { status: 404 });
  }
}
```

Separate classes and bindings make the isolation structural — there is no shared namespace to accidentally collide in.

---

## Prevention / Detection

```bash
# Grep for idFromName calls and check that every call site uses a feature prefix or a dedicated binding
grep -rn 'idFromName' ./src --include='*.ts' \
  | awk -F: '{print $1": "$3}' \
  | sort
```

```typescript
// Helper that enforces a prefix convention at the call site
function cartDOId(env: Env, userId: string): DurableObjectId {
  // The prefix is hardcoded here; callers cannot forget it
  return env.CART_DO.idFromName(`cart:${userId}`);
}

function reservationDOId(env: Env, userId: string): DurableObjectId {
  return env.RESERVATION_DO.idFromName(`reservation:${userId}`);
}

// Unit test: verify the two helpers produce different IDs for the same userId
import { describe, it, expect } from 'vitest';

describe('DO id helpers', () => {
  it('produce distinct IDs for cart and reservation', () => {
    const env = getMockEnv(); // test double with deterministic idFromName
    const userId = 'user-123';
    expect(cartDOId(env, userId).toString()).not.toBe(
      reservationDOId(env, userId).toString(),
    );
  });
});
```

---

## Anti-patterns

- **Shared DO class for unrelated features** — a DO's storage is a flat key-value store; two features sharing one instance must agree on every storage key, which is fragile and couples unrelated code.
- **Using raw entity IDs (userId, orderId) as DO names without a prefix** — the name is the entire identity; two features that both consider a userId to be the natural key will always collide.
- **Treating wrangler.toml binding names as namespaces** — `idFromName` hashes (binding-class, name); if two bindings point to the same class, collisions are still possible.

---

## Gotchas

- Changing an `idFromName` prefix is a **breaking migration**. The old DO instance still exists and holds old state. You must write a migration Worker that reads from old IDs and writes to new IDs before decommissioning old instances.
- DO instances are never automatically garbage-collected. Orphaned instances (from the old un-prefixed names) accumulate storage costs until explicitly deleted via the REST API.
- `idFromName` is not reversible — you cannot look up what name was used to produce a given ID. Store the canonical name (with prefix) alongside any data that needs to be re-keyed.
- In local development with `wrangler dev`, DO state is in-memory and resets on restart, masking collisions that only appear in production where state persists across requests.

---

## Verification

```bash
# 1. After deploying the prefixed fix, verify cart and reservation return isolated data
# Cart endpoint
curl -s -H 'X-User-Id: user-123' https://api.example.com/cart | jq '.'

# Reservation endpoint
curl -s -H 'X-User-Id: user-123' https://api.example.com/inventory/reservation | jq '.'

# 2. Confirm no reservation keys appear in cart response and vice versa
curl -s -H 'X-User-Id: user-123' https://api.example.com/cart \
  | jq 'has("reservation")'
# Expected: false

# 3. Check for stale un-prefixed DO instances via the DO namespace API
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/workers/durable_objects/namespaces/${DO_NAMESPACE_ID}/objects" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result | length'
```

---

## Related

- `lessons-workers-fetch-timeout-no-deadline.md`

---

## Sources

- Cloudflare Durable Objects — idFromName — https://developers.cloudflare.com/durable-objects/api/namespace/#idfromname
- Cloudflare Durable Objects Storage API — https://developers.cloudflare.com/durable-objects/api/storage-api/
- Durable Objects Best Practices — https://developers.cloudflare.com/durable-objects/best-practices/
