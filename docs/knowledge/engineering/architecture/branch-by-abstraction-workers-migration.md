# Branch by Abstraction — Feature Migration in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to replace a large chunk of implementation (a data-access layer, an external API
client, a pricing engine) inside a live Cloudflare Worker without a flag-day cutover.
Deploying an entirely new Worker for the replacement is not feasible because the logic is
deeply embedded in request-handling code shared with many other features.

Branch by Abstraction lets you migrate incrementally inside the same Worker codebase,
routing calls through an interface that switches between old and new implementations
without requiring a single big-bang release.

---

## Context

Martin Fowler's Branch by Abstraction (BbA) is a trunk-based technique:

1. Introduce an abstraction (interface / type) over the code to be replaced.
2. Make existing code call the abstraction instead of the implementation directly.
3. Build the new implementation behind the same interface.
4. Gradually move callers to the new implementation (or use a feature flag to switch).
5. Remove the old implementation once no callers remain.

In the Workers runtime the pattern plays well because:

- Workers are deployed as a single bundle; there is no staging branch that diverges.
- Service bindings and KV flags make per-request routing cheap.
- Durable Objects can hold migration-state (which percentage of traffic uses new path).

---

## Step 1 — Define the Abstraction

```typescript
// src/ports/pricing.ts
export interface PricingPort {
  calculate(skuId: string, qty: number, ctx: ExecutionContext): Promise<number>;
}
```

---

## Step 2 — Wrap the Old Implementation

```typescript
// src/adapters/pricing-legacy.ts
import type { PricingPort } from "../ports/pricing";

export class LegacyPricingAdapter implements PricingPort {
  private readonly legacyService: Service; // service binding to old Worker

  constructor(legacyService: Service) {
    this.legacyService = legacyService;
  }

  async calculate(skuId: string, qty: number, ctx: ExecutionContext): Promise<number> {
    const res = await this.legacyService.fetch(
      new Request(`https://pricing/calculate?sku=${skuId}&qty=${qty}`)
    );
    if (!res.ok) throw new Error(`Legacy pricing failed: ${res.status}`);
    const { price } = await res.json<{ price: number }>();
    return price;
  }
}
```

---

## Step 3 — Build the New Implementation

```typescript
// src/adapters/pricing-new.ts
import type { PricingPort } from "../ports/pricing";
import type { D1Database } from "@cloudflare/workers-types";

export class NewPricingAdapter implements PricingPort {
  constructor(private readonly db: D1Database) {}

  async calculate(skuId: string, qty: number, _ctx: ExecutionContext): Promise<number> {
    const row = await this.db
      .prepare("SELECT unit_price, tier_discount FROM pricing WHERE sku_id = ?")
      .bind(skuId)
      .first<{ unit_price: number; tier_discount: number }>();

    if (!row) throw new Error(`No pricing for sku ${skuId}`);
    const discount = qty >= 10 ? row.tier_discount : 0;
    return row.unit_price * qty * (1 - discount);
  }
}
```

---

## Step 4 — Router that Switches Between Implementations

```typescript
// src/adapters/pricing-router.ts
import type { PricingPort } from "../ports/pricing";

export type MigrationState = "legacy" | "shadow" | "new";

export class PricingRouter implements PricingPort {
  constructor(
    private readonly legacy: PricingPort,
    private readonly next: PricingPort,
    private readonly state: MigrationState,
    private readonly ctx: ExecutionContext
  ) {}

  async calculate(skuId: string, qty: number, ctx: ExecutionContext): Promise<number> {
    switch (this.state) {
      case "legacy":
        return this.legacy.calculate(skuId, qty, ctx);

      case "shadow": {
        // Run both; return legacy result; log divergence
        const [legacyPrice, newPrice] = await Promise.allSettled([
          this.legacy.calculate(skuId, qty, ctx),
          this.next.calculate(skuId, qty, ctx),
        ]);

        if (legacyPrice.status === "rejected") throw legacyPrice.reason;

        if (
          newPrice.status === "rejected" ||
          Math.abs(newPrice.value - legacyPrice.value) > 0.01
        ) {
          // waitUntil so logging doesn't block response
          this.ctx.waitUntil(
            logDivergence(skuId, qty, legacyPrice.value, newPrice)
          );
        }

        return legacyPrice.value;
      }

      case "new":
        return this.next.calculate(skuId, qty, ctx);
    }
  }
}

async function logDivergence(
  skuId: string,
  qty: number,
  legacyPrice: number,
  newResult: PromiseSettledResult<number>
): Promise<void> {
  console.log(JSON.stringify({
    event: "pricing_divergence",
    skuId,
    qty,
    legacyPrice,
    newPrice: newResult.status === "fulfilled" ? newResult.value : null,
    newError: newResult.status === "rejected" ? String(newResult.reason) : null,
  }));
}
```

---

## Step 5 — Wire Up in the Worker Entry Point

```typescript
// src/index.ts
import { LegacyPricingAdapter } from "./adapters/pricing-legacy";
import { NewPricingAdapter } from "./adapters/pricing-new";
import { PricingRouter, type MigrationState } from "./adapters/pricing-router";

export interface Env {
  LEGACY_PRICING: Service;
  DB: D1Database;
  PRICING_STATE: KVNamespace; // holds "legacy" | "shadow" | "new"
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const state = ((await env.PRICING_STATE.get("state")) ?? "legacy") as MigrationState;

    const pricing = new PricingRouter(
      new LegacyPricingAdapter(env.LEGACY_PRICING),
      new NewPricingAdapter(env.DB),
      state,
      ctx
    );

    // ... rest of handler uses `pricing` through the PricingPort interface
    const price = await pricing.calculate("SKU-001", 5, ctx);
    return Response.json({ price });
  },
};
```

---

## Migration Sequence

```
KV write: PRICING_STATE = "legacy"   # baseline — all traffic to old path
KV write: PRICING_STATE = "shadow"   # parallel execution; legacy wins; divergences logged
    ↓ monitor divergences for N days / requests
KV write: PRICING_STATE = "new"      # new path serves all traffic
    ↓ delete LegacyPricingAdapter, old service binding, KV key
```

Because the KV write takes effect on the next request (with up to 60 s eventual consistency),
no redeployment is needed to advance the migration state.

---

## Anti-patterns

**Skipping shadow mode.** Moving directly from `legacy` to `new` removes the opportunity to
catch divergences in production data. Shadow mode is cheap—run it for at least 48 h across
varied traffic.

**Leaking the implementation type into call sites.** Callers importing `LegacyPricingAdapter`
directly cannot be easily switched. Every caller must depend only on `PricingPort`.

**Forgetting cleanup.** Leaving both adapters in the bundle after cutover bloats the Worker
and creates confusion about which path is active. Remove the old adapter in a follow-up
deploy once `state = "new"` has been stable for a sprint.

**Long-lived shadow mode.** Shadow mode adds latency (both calls run in parallel) and can
mask new bugs if nobody monitors the divergence logs. Set a calendar reminder to exit shadow
mode within a defined window.

---

## Gotchas

- KV `get` in the hot path adds ~1–3 ms. Cache the value in a module-level variable with a
  short TTL (e.g., refresh once per minute) to avoid paying this on every request.
- The `shadow` state doubles external calls to the data source. Ensure rate limits and
  billing budgets account for the temporary 2× load.
- `Promise.allSettled` swallows rejections from the new path during shadow mode. Add explicit
  error-rate metrics so a persistently broken new adapter is caught before you flip to `"new"`.

---

## Verification

```bash
# Set state to shadow
wrangler kv key put --namespace-id=<NS_ID> state shadow

# Tail the Worker logs for divergence events
wrangler tail --format pretty | grep pricing_divergence

# Confirm zero divergences over 10 k requests, then promote
wrangler kv key put --namespace-id=<NS_ID> state new
```

---

## Related

- `strangler-fig-cloudflare-migration.md` — coarser-grained replacement at the Worker boundary
- `feature-flag-cloudflare-workers-kv.md` — KV-backed feature flag mechanics
- `dual-write-problem-queues-workers.md` — problems that arise when writing to two stores simultaneously
- `a-b-testing-architecture.md` — traffic-split techniques

---

## Sources

- Martin Fowler, "Branch By Abstraction", martinfowler.com/bliki/BranchByAbstraction.html
- Cloudflare KV docs — `workers.cloudflare.com/docs/runtime-apis/kv`
- Cloudflare Service Bindings — `workers.cloudflare.com/docs/runtime-apis/bindings/service-bindings`
