# Strategy Pattern: Runtime Algorithm Selection via KV Config

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Worker needs to choose between multiple algorithms or behaviours at runtime—tax calculation rules by jurisdiction, pricing tiers per tenant, content ranking algorithms per A/B cohort, retry policies per environment. Hard-coding the choice with `if/else` chains works until you have more than two variants and ops needs to change the active algorithm without a code deploy.

Classic signs:
- `if (region === "EU") { ... } else if (region === "US") { ... }` branches growing uncontrolled
- Changing the "active" algorithm requires a deploy and rollback risk
- A/B testing between algorithms is manual and error-prone
- Different tenants need different business logic for the same endpoint

---

## Context

The Strategy pattern defines a family of algorithms, encapsulates each one, and makes them interchangeable. In a Workers context, the active strategy key is stored in KV (hot, low-latency) and resolved at request time. The Worker reads the key, selects the correct strategy object from an in-memory registry, and delegates to it. No deploy is needed to change which strategy is active.

```
KV: "strategy:pricing:tenant-acme" → "volume_discount"
                     │
              Worker reads at request time
                     │
             Strategy registry lookup
                     │
          VolumeDiscountStrategy.calculate()
```

---

## Defining the Strategy Interface

```typescript
// src/pricing/types.ts
export interface LineItem {
  sku: string;
  qty: number;
  unitPriceCents: number;
}

export interface PricingContext {
  tenantId: string;
  items: LineItem[];
  couponCode?: string;
}

export interface PricingResult {
  subtotalCents: number;
  discountCents: number;
  totalCents: number;
  strategyUsed: string;
}

export interface PricingStrategy {
  readonly name: string;
  calculate(ctx: PricingContext): PricingResult;
}
```

---

## Concrete Strategies

```typescript
// src/pricing/strategies.ts
import type { PricingStrategy, PricingContext, PricingResult } from "./types";

export class FlatRateStrategy implements PricingStrategy {
  readonly name = "flat_rate";

  calculate({ items }: PricingContext): PricingResult {
    const subtotalCents = items.reduce((s, i) => s + i.qty * i.unitPriceCents, 0);
    return { subtotalCents, discountCents: 0, totalCents: subtotalCents, strategyUsed: this.name };
  }
}

export class VolumeDiscountStrategy implements PricingStrategy {
  readonly name = "volume_discount";

  calculate({ items }: PricingContext): PricingResult {
    const subtotalCents = items.reduce((s, i) => s + i.qty * i.unitPriceCents, 0);
    const totalQty = items.reduce((s, i) => s + i.qty, 0);

    // 5% off ≥10 units, 15% off ≥50 units
    const rate = totalQty >= 50 ? 0.15 : totalQty >= 10 ? 0.05 : 0;
    const discountCents = Math.round(subtotalCents * rate);

    return {
      subtotalCents,
      discountCents,
      totalCents: subtotalCents - discountCents,
      strategyUsed: this.name,
    };
  }
}

export class SubscriberStrategy implements PricingStrategy {
  readonly name = "subscriber";

  calculate({ items, couponCode }: PricingContext): PricingResult {
    const subtotalCents = items.reduce((s, i) => s + i.qty * i.unitPriceCents, 0);
    const couponDiscount = couponCode === "LOYALTY10" ? 0.1 : 0;
    const subscriberDiscount = 0.08;
    const rate = Math.min(couponDiscount + subscriberDiscount, 0.25);
    const discountCents = Math.round(subtotalCents * rate);

    return {
      subtotalCents,
      discountCents,
      totalCents: subtotalCents - discountCents,
      strategyUsed: this.name,
    };
  }
}
```

---

## Strategy Registry

```typescript
// src/pricing/registry.ts
import type { PricingStrategy } from "./types";
import { FlatRateStrategy, VolumeDiscountStrategy, SubscriberStrategy } from "./strategies";

const DEFAULT_STRATEGY = "flat_rate";

const REGISTRY = new Map<string, PricingStrategy>([
  ["flat_rate", new FlatRateStrategy()],
  ["volume_discount", new VolumeDiscountStrategy()],
  ["subscriber", new SubscriberStrategy()],
]);

export function getStrategy(name: string): PricingStrategy {
  const strategy = REGISTRY.get(name);
  if (!strategy) {
    console.warn(`Unknown strategy "${name}", falling back to ${DEFAULT_STRATEGY}`);
    return REGISTRY.get(DEFAULT_STRATEGY)!;
  }
  return strategy;
}

export function listStrategies(): string[] {
  return [...REGISTRY.keys()];
}
```

---

## Worker: Resolving Strategy from KV

```typescript
// src/worker.ts
import { getStrategy } from "./pricing/registry";
import type { PricingContext } from "./pricing/types";

export interface Env {
  CONFIG: KVNamespace;
}

// Module-level cache: strategy name per tenant, short TTL avoids cold KV reads
const strategyCache = new Map<string, { name: string; expiresAt: number }>();
const CACHE_TTL_MS = 30_000; // 30 s

async function resolveStrategyName(tenantId: string, kv: KVNamespace): Promise<string> {
  const cached = strategyCache.get(tenantId);
  if (cached && cached.expiresAt > Date.now()) return cached.name;

  // Tenant-specific override, falling back to global default
  const name =
    (await kv.get(`strategy:pricing:${tenantId}`)) ??
    (await kv.get("strategy:pricing:default")) ??
    "flat_rate";

  strategyCache.set(tenantId, { name, expiresAt: Date.now() + CACHE_TTL_MS });
  return name;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const ctx = await request.json<PricingContext>();
    if (!ctx.tenantId || !ctx.items?.length) {
      return new Response("Bad Request", { status: 400 });
    }

    const strategyName = await resolveStrategyName(ctx.tenantId, env.CONFIG);
    const strategy = getStrategy(strategyName);
    const result = strategy.calculate(ctx);

    return Response.json(result);
  },
};
```

---

## Admin Endpoint: Changing the Active Strategy

```typescript
// src/admin-worker.ts — protected by auth middleware (omitted for brevity)
export interface Env {
  CONFIG: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "PUT" && url.pathname === "/strategy/pricing") {
      const { tenantId, strategyName } = await request.json<{
        tenantId?: string;
        strategyName: string;
      }>();

      const key = tenantId
        ? `strategy:pricing:${tenantId}`
        : "strategy:pricing:default";

      await env.CONFIG.put(key, strategyName);

      return Response.json({ ok: true, key, strategyName });
    }

    if (request.method === "GET" && url.pathname === "/strategy/pricing") {
      const tenantId = url.searchParams.get("tenantId");
      const key = tenantId
        ? `strategy:pricing:${tenantId}`
        : "strategy:pricing:default";
      const value = await env.CONFIG.get(key);
      return Response.json({ key, strategyName: value ?? "flat_rate (default)" });
    }

    return new Response("Not found", { status: 404 });
  },
};
```

---

## Anti-patterns

- **Putting strategy logic in KV values**: KV should store the strategy *name* (a string), never executable code or JSON rule trees large enough to constitute a mini-engine. Complex rule data belongs in D1; the strategy object in Workers interprets it.
- **A single giant `switch` in the Worker**: This is the pattern the Strategy pattern replaces. A switch statement forces a deploy to add a new strategy. Use the registry map instead.
- **Shared mutable state inside strategy objects**: Strategy instances in the module-level registry are shared across all requests on the same isolate. Strategies must be stateless and thread-safe (Workers are single-threaded per isolate, but isolates are shared across requests).
- **No fallback strategy**: If KV returns `null` (network glitch, key deleted), the Worker should fall back to a safe default, not throw a 500.
- **Cache TTL too long**: A 10-minute module-level cache means an ops change to the active strategy takes 10 minutes to propagate. Keep the TTL under 60 seconds for operational agility.

---

## Gotchas

- Workers are not guaranteed to run in the same isolate across requests. Module-level cache (`strategyCache`) is per-isolate, so after an isolate recycle the first request pays a KV read. This is acceptable; it is not a bug.
- KV has ~40 ms median read latency from many regions. The module-level cache amortises this across requests in the same isolate.
- If strategy resolution is on the critical path for every request and latency is critical, consider storing the strategy name in a Durable Object alarm-refreshed cache instead of raw KV.
- `listStrategies()` is useful for the admin UI's dropdown. Keep it updated as you add new strategy implementations; the registry is the source of truth for valid names.
- Strategy names stored in KV are strings—validate them against `REGISTRY.has(name)` before storing in the admin endpoint to prevent silent fallback confusion later.

---

## Verification

1. POST a pricing request for tenant `acme` with no KV key set; confirm `strategyUsed: "flat_rate"` in the response.
2. PUT `strategy:pricing:acme → "volume_discount"` via the admin endpoint and POST 50-unit order; confirm `discountCents > 0` and `strategyUsed: "volume_discount"`.
3. Set an invalid strategy name in KV and confirm the Worker falls back to `flat_rate` without throwing.
4. Confirm the module-level cache is used: add a log in `resolveStrategyName` and send 10 requests within 30 s; confirm only 1 KV read appears.
5. Add a new `GeoDiscountStrategy` to the registry without changing the Worker entrypoint; confirm it is selectable via the admin endpoint immediately.

---

## Related

- `feature-flags-implementations.md` — toggling features without deploy
- `cache-aside-kv-d1-fallback.md` — caching patterns for KV
- `per-tenant-durable-object.md` — per-tenant isolation at the DO level
- `dependency-injection.md` — injecting strategy dependencies in larger systems

---

## Sources

- Gang of Four — Design Patterns (1994): Strategy pattern
- Cloudflare KV API: https://developers.cloudflare.com/kv/api/
- Cloudflare Workers module-level globals: https://developers.cloudflare.com/workers/reference/security-model/
