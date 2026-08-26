# Workers KV Write-After-Read Consistency Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A coupon-redemption Worker read a KV key to confirm a coupon was unused, marked it redeemed, and wrote it back — yet users were occasionally able to redeem the same coupon twice, triggering a double-discount on checkout.

## Context
Cloudflare Workers KV is an eventually consistent global store with read-after-write consistency only within the same data-center colo. When a Worker reads from KV, the colo serving the read may not yet have propagated a write that was committed milliseconds earlier by a different colo. Under normal single-user traffic this is invisible; under concurrent global traffic (or a user hitting retry fast enough to land on a different edge node) the stale read window is exposed.

The coupon service ran entirely inside Workers with no Durable Object layer. The assumption "I just wrote this key, so my next read will reflect it" held locally but broke globally. Incident cost: ~$4,200 in fraudulently applied discounts over a 72-hour window before detection.

---

## Architecture / Root Cause

The original redemption flow:

```typescript
// workers/coupon-redeem.ts  — BUGGY PATTERN
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const couponId = new URL(request.url).searchParams.get("coupon");
    if (!couponId) return new Response("Missing coupon", { status: 400 });

    // Step 1: read current state
    const raw = await env.COUPONS.get(couponId, { type: "json" }) as CouponRecord | null;
    if (!raw) return new Response("Not found", { status: 404 });

    // Step 2: guard
    if (raw.redeemed) {
      return new Response("Already redeemed", { status: 409 });
    }

    // Step 3: write — THIS WRITE IS NOT IMMEDIATELY GLOBALLY VISIBLE
    await env.COUPONS.put(couponId, JSON.stringify({ ...raw, redeemed: true }));

    // Step 4: downstream charge — irreversible
    await chargeDiscount(env, raw);

    return new Response("OK");
  },
};
```

Two concurrent requests from different PoPs both read `redeemed: false` before either write propagated, passed the guard, and both proceeded to `chargeDiscount`.

---

## Correct Pattern — Durable Object as Serialization Fence

Move the compare-and-swap into a Durable Object, which guarantees single-threaded execution per instance:

```typescript
// durable-objects/CouponLock.ts
export class CouponLock implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const { couponId } = await request.json<{ couponId: string }>();

    // DO storage is strongly consistent within the instance
    const redeemed = await this.state.storage.get<boolean>("redeemed");
    if (redeemed) {
      return Response.json({ ok: false, reason: "already_redeemed" }, { status: 409 });
    }

    // Atomic claim — next request on this instance sees redeemed = true
    await this.state.storage.put("redeemed", true);
    return Response.json({ ok: true });
  }
}
```

```typescript
// workers/coupon-redeem.ts  — FIXED
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const couponId = new URL(request.url).searchParams.get("coupon");
    if (!couponId) return new Response("Missing coupon", { status: 400 });

    // Route to the DO instance whose name is the coupon ID
    const id = env.COUPON_LOCK.idFromName(couponId);
    const stub = env.COUPON_LOCK.get(id);

    const lockResp = await stub.fetch(new Request("https://do/claim", {
      method: "POST",
      body: JSON.stringify({ couponId }),
      headers: { "Content-Type": "application/json" },
    }));

    if (!lockResp.ok) {
      const { reason } = await lockResp.json<{ reason: string }>();
      return new Response(reason, { status: 409 });
    }

    // KV write is now for cache/reporting only — not for guarding
    const raw = await env.COUPONS.get(couponId, { type: "json" }) as CouponRecord;
    await chargeDiscount(env, raw);

    // Best-effort KV update for analytics; DO remains the source of truth
    await env.COUPONS.put(couponId, JSON.stringify({ ...raw, redeemed: true }), { expirationTtl: 86400 });

    return new Response("OK");
  },
};
```

---

## Wrangler Binding Configuration

```jsonc
// wrangler.jsonc
{
  "durable_objects": {
    "bindings": [
      { "name": "COUPON_LOCK", "class_name": "CouponLock" }
    ]
  },
  "kv_namespaces": [
    { "binding": "COUPONS", "id": "<KV_NAMESPACE_ID>" }
  ],
  "migrations": [
    { "tag": "v1", "new_classes": ["CouponLock"] }
  ]
}
```

---

## Anti-patterns
- Using KV `get` → `put` as an optimistic lock — KV has no CAS primitive.
- Relying on KV write-after-read consistency across PoPs; it only holds within the same colo.
- Keeping the guard logic in a Worker and the authoritative store in KV; they have different consistency guarantees.
- Treating a KV `put` return value as proof that the next `get` anywhere in the world will see the new value.
- Using `expirationTtl` on guard keys — expiry does not change the consistency model.

## Gotchas
- Durable Object `idFromName` is deterministic: the same string always routes to the same instance globally, which is exactly what you want for per-resource serialization.
- DO storage `put` inside a DO fetch handler is synchronous-from-the-caller's-perspective but still async; always `await` it before returning the claim result.
- A DO instance can be evicted between calls; `this.state.storage` persists across evictions but in-memory fields do not — never hold lock state in a class property.
- `chargeDiscount` must still be idempotent because network retries can re-invoke the Worker even after a DO claim succeeds.
- KV eventual consistency window is typically under 60 seconds globally but is not bounded by SLA.

## Verification

```bash
# Smoke-test concurrent redemption attempts using wrk or hey
hey -n 50 -c 50 "https://api.example.com/coupon/redeem?coupon=TEST-COUPON-001"
# Expect: exactly 1 × 200, 49 × 409

# Confirm DO storage persisted the claim
wrangler durable-objects inspect --class CouponLock --id <INSTANCE_ID>
```

```sql
-- If chargeDiscount writes to D1, verify idempotency
SELECT coupon_id, COUNT(*) as redemptions
FROM discount_events
GROUP BY coupon_id
HAVING COUNT(*) > 1;
-- Should return 0 rows
```

## Related
- `durable-objects-storage-transaction-atomicity-lesson.md`
- `kv-consistency-mode-eventual-reads-production-bug.md`
- `kv-ttl-expiry-race-condition-session-logout-incident.md`
- `idempotency-keys-for-all-payment-calls.md`
- `cloudflare-storage-primitive-selection.md`

## Sources
- https://developers.cloudflare.com/kv/concepts/how-kv-works/#consistency
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/durable-objects/
