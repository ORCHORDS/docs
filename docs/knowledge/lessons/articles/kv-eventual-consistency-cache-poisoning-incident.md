# KV Eventual Consistency — Cache Poisoning Incident

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A product availability update — specifically, a product being marked as discontinued and removed from the catalog — resulted in customers being able to add that product to their cart and place orders for up to 60 seconds after removal. The product data had been deleted from D1 (the source of truth) and a KV delete had been issued, but edge nodes in certain regions continued serving the stale KV-cached value for the duration of its TTL. The business impact was real: 14 orders were placed for a discontinued item before the TTL expired globally.

---

## Context

The platform cached product data in Cloudflare KV for performance. The read path was:

1. Worker receives `GET /api/products/:id`.
2. Worker reads from KV (`product:{id}`).
3. On KV hit: return cached data.
4. On KV miss: read from D1, write to KV with `expirationTtl: 60`, return data.

KV writes used `put` with a 60-second TTL. When a product was discontinued, the operations were:

```typescript
// Product discontinuation handler
await env.DB.prepare('DELETE FROM products WHERE id = ?').bind(productId).run();
await env.KV.delete(`product:${productId}`);
```

This looks correct but is not safe. KV's consistency model is **eventual consistency across edge nodes**. A `delete` propagates to all edge PoPs, but propagation is not instantaneous — it can take up to 60 seconds in practice (and occasionally longer). During that window, edge nodes that had not yet received the delete continued to serve the cached value.

**Stack:**
- Cloudflare KV (globally distributed, eventually consistent)
- Cloudflare D1 (single-region, strongly consistent)
- Cloudflare Workers (product API)
- Cart and order service (separate Worker, reads product availability before accepting order)

---

## Incident Timeline

### 2026-07-14

- `15:03 UTC` — Catalog admin marks product `SKU-88821` as discontinued. Discontinuation handler runs: D1 DELETE + KV DELETE.
- `15:03–15:05 UTC` — Edge nodes in `CDG` (Paris), `NRT` (Tokyo), and `GRU` (São Paulo) continue serving stale KV value for `product:SKU-88821` with `available: true`.
- `15:03–15:05 UTC` — Cart service (reading product availability from KV) approves 14 add-to-cart events for `SKU-88821` and 14 orders are created in the order service.
- `15:05 UTC` — KV delete propagates globally. `SKU-88821` no longer served from KV. Remaining requests correctly return 404.
- `15:11 UTC` — Support ticket filed: customers receiving order confirmations for a discontinued item.
- `15:24 UTC` — Engineering alerted. Root cause identified as KV eventual consistency window.
- `15:45 UTC` — 14 affected orders manually cancelled and refunded. Customer support emails sent.

---

## Root Cause

KV is an **eventually consistent** store. The official documentation states propagation "typically" completes in under 60 seconds but makes no strong consistency guarantee. The architecture assumed that issuing a KV `delete` was equivalent to an immediate global removal — this assumption is incorrect.

The cart service read product availability exclusively from KV, which meant the availability check was subject to the consistency window of KV, not the strong consistency of D1.

The combination of:
- A 60-second TTL on KV values, and
- KV delete propagation latency of up to 60 seconds

...created a window where the KV value could outlive its intended validity by up to 2x the TTL in the worst case.

---

## Fix — D1 for Transactional Truth, KV for Enrichment Only

### Before (incorrect — availability from KV)

```typescript
// cart-service/src/add-to-cart.ts
async function checkAvailability(productId: string, env: Env): Promise<boolean> {
  const cached = await env.KV.get(`product:${productId}`, 'json') as ProductData | null;
  if (cached) return cached.available; // BUG: KV may be stale after delete
  const row = await env.DB.prepare(
    'SELECT available FROM products WHERE id = ?'
  ).bind(productId).first();
  return row?.available ?? false;
}
```

### After (correct — availability from D1)

```typescript
// cart-service/src/add-to-cart.ts
async function checkAvailability(productId: string, env: Env): Promise<boolean> {
  // Transactional truth always comes from D1 for availability checks
  const row = await env.DB.prepare(
    'SELECT available FROM products WHERE id = ? AND available = 1'
  ).bind(productId).first();
  return row !== null;
}

async function getProductEnrichment(productId: string, env: Env): Promise<ProductEnrichment | null> {
  // Non-critical enrichment (description, images, tags) can still come from KV
  return env.KV.get(`product:enrichment:${productId}`, 'json');
}
```

### Updated KV Usage Pattern

```typescript
// Only cache non-transactional, non-availability data in KV
const ENRICHMENT_TTL = 300; // 5 minutes — acceptable staleness for descriptions

async function cacheEnrichment(productId: string, data: ProductEnrichment, env: Env) {
  await env.KV.put(
    `product:enrichment:${productId}`,
    JSON.stringify(data),
    { expirationTtl: ENRICHMENT_TTL }
  );
}

// On product discontinuation — enrichment delete is best-effort;
// the D1 availability check is the safety gate regardless
async function discontinueProduct(productId: string, env: Env) {
  await env.DB.prepare(
    'UPDATE products SET available = 0, discontinued_at = ? WHERE id = ?'
  ).bind(new Date().toISOString(), productId).run();
  // KV delete is best-effort — D1 is the source of truth for availability
  await env.KV.delete(`product:enrichment:${productId}`).catch(() => {});
}
```

---

## Pattern Decision: KV for Configuration, D1 for Transactional Truth

This incident produced a formal architectural decision recorded in `docs/adr/ADR-2026-007.md`:

> **ADR-2026-007: Data Store Selection for Cloudflare Workers**
>
> - **KV**: Use for configuration, feature flags, non-transactional enrichment data (product descriptions, tag metadata, locale strings), and data where eventual consistency over 60s is acceptable and the cost of staleness is low.
> - **D1**: Use for transactional truth — availability, inventory, pricing, user entitlements, order state. Any field whose staleness has a direct business or safety impact must be read from D1.
> - **Never use KV as the sole availability gate for transactional operations.** KV deletes are not atomic globally; a concurrent read in another region may still succeed during propagation.

---

## Anti-patterns / What Went Wrong

1. **Using KV as the availability check for transactional operations.** KV eventual consistency is well-documented but easy to overlook when building fast. The team optimized for low-latency reads without accounting for the consistency cost.

2. **Assuming `kv.delete()` is synchronous globally.** It is not. It queues a propagation to all edge nodes, which completes eventually, not immediately.

3. **Short TTLs do not protect against this.** A 60-second TTL does not help if the propagation of the delete itself takes 60 seconds. The TTL and the propagation latency can compound.

4. **No integration test for the discontinuation flow end-to-end.** A test that mocked KV as consistent would not have caught this. Only an end-to-end test with real KV (or a mock that simulates propagation delay) would have revealed the race.

---

## Gotchas

- **KV consistency guarantees are "read your own writes" per-PoP, not globally.** A write from a Worker in `IAD` is immediately readable by the next request routed to `IAD`, but not necessarily by a request routed to `NRT` milliseconds later.
- **KV TTL and propagation latency are additive in the worst case.** If a value has a 60s TTL and propagation takes 60s, a stale reader can serve the old value for up to 120s after a delete.
- **D1 read latency is acceptable for transactional checks.** D1 query latency (5–15ms for a simple indexed lookup) is negligible compared to the business risk of stale availability data from KV.
- **Feature flags in KV are generally safe.** A feature flag that is stale for 60s has low consequence. A product availability flag that is stale for 60s during a high-traffic moment has material business impact. Know the difference.
- **KV `getWithMetadata` does not help with consistency.** Metadata is cached at the same edge PoP and subject to the same consistency window.

---

## Verification

- Post-fix: 0 orders for unavailable products in the 30 days following remediation.
- Cart service availability check confirmed reading from D1 via code review and integration test.
- ADR-2026-007 reviewed and accepted by engineering leads.
- Staging test added: discontinue a product, immediately fire 50 concurrent cart add requests from Workers in multiple regions, assert 0 succeed.

---

## Related

- `d1-missing-index-full-table-scan-viral-traffic.md`
- `durable-objects-alarm-delivery-guarantee-lesson.md`
- Cloudflare KV: [How KV works — consistency](https://developers.cloudflare.com/kv/learning/how-kv-works/)
- Cloudflare D1: [Getting started](https://developers.cloudflare.com/d1/)
- Internal ADR: `docs/adr/ADR-2026-007.md`

---

## Sources

- Internal incident report `INC-2026-0714`
- Customer support tickets `SUP-2026-7441` through `SUP-2026-7454`
- Cloudflare KV consistency documentation
- Architecture decision record `ADR-2026-007`
