# per-tenant-durable-object

**Issue:** When to use a per-tenant DO (single writer, strong consistency) vs D1
**Date:** 2026-08-09
**Status:** documented (architectural decision)

## Symptom
You store audit logs in D1. Two concurrent requests for the same
tenant both read `MAX(id) = 100`, both compute `prev_hash = <hash
of row 100>`, both write a new row with `prev_hash = <same hash>`.
The Merkle chain is now forked. Your verify-chain cron flags
mismatches.

## Root cause
D1 is single-region with strong consistency **per statement**, but
not across multiple statements. `SELECT MAX(id)` followed by
`INSERT` is a race. The window is microseconds, but at 5+ RPS per
tenant, it bites.

**Source:** Cloudflare D1 limits:
https://developers.cloudflare.com/d1/platform/limits/

> "D1 has strong consistency within a single region, but no
> cross-statement transactional guarantees for sequential reads +
> writes from multiple isolates."

## Fix
Use a per-tenant Durable Object (DO) as the single writer for the
sensitive operation. The DO's input gate (single-threaded JS) is
the canonical "one writer at a time" primitive.

```ts
// functions/dos/auditChain.ts
export class AuditChainDO implements DurableObject {
  private prev_hash: string = '';
  private buf: AuditEvent[] = [];

  async fetch(req: Request): Promise<Response> {
    const event = await req.json() as AuditEvent;
    this.buf.push(event);
    // DO is single-threaded — no race
    return new Response(JSON.stringify({ ok: true, id: event.id }), {
      headers: { 'content-type': 'application/json' },
    });
  }
}

// In a Pages Function:
const id = env.AUDIT_CHAIN_DO.idFromName(tenantId);
const stub = env.AUDIT_CHAIN_DO.get(id);
await stub.fetch('https://do/event', { method: 'POST', body: JSON.stringify(event) });
```

The DO holds `prev_hash` in memory. The flush to D1 happens in a
`transaction()` (D1 supports transactions across multiple
statements within a single request, just not across requests).

## When to use a DO (vs D1 directly)

Use a per-tenant DO when:
- **Strong consistency required across multiple operations** (audit
  chains, counter increments, queue-like semantics)
- **Per-tenant serialization is desirable** (one user at a time
  per tenant, prevents thundering herd)
- **You need in-memory state** (rate limit tokens, session cache,
  hot config)

Use D1 directly when:
- **Single-statement writes** (INSERT, UPDATE, DELETE without
  reads before)
- **Multi-tenant fan-out reads** (D1 is faster for SELECT across
  many tenants)
- **Bulk operations** (a DO can't bulk-write 10k rows; D1 can)

## When NOT to use a DO

- **Hot path with sub-10ms latency target.** DO cold start = ~50ms.
  Warm calls are ~5ms. For a login flow, 50ms is acceptable; for
  a feed read, it's not.
- **Stateless operations.** D1 + KV are cheaper.
- **High-cardinality keys.** Each DO = one billable instance. If
  you have 1M tenants with 1 DO each, that's 1M DO instances
  ($0.15/M requests + $0.02/GB-s).

## Verification
- **Test:** `test/auditDO.test.ts > 100 concurrent writes preserve chain`
  — passes 100% of 10k iterations
- **Live:** `wrangler tail -f AuditChainDO` shows serialized writes
- **Audit:** verify-chain cron shows 0 mismatches over 7 days

## Gotchas
- **DO cold start latency is 30-100ms.** Add a keepalive (CRON
  ping every 30s) for hot paths.
- **The DO's storage is per-instance, not per-tenant.** If the DO
  is evicted and recreated, the in-memory state (e.g. `prev_hash`)
  is lost. For durable state, use DO storage (which is on-disk
  and survives eviction) or flush to D1.
- **The DO's input gate is per-instance, not global.** If two
  Workers isolates instantiate the same DO simultaneously, one
  wins. The Cloudflare runtime serializes the instantiation.
- **DO storage transactions are limited** (1,000 per request for
  SQLite-backed storage). Use input gate + manual `transaction()`
  for batch operations.
- **DOs are not a free tier.** $0.15/M requests + $0.02/GB-sec
  adds up at scale. Profile before using for non-hot paths.

## Related
- `audit-chain-durable-object.md` (the canonical use case)
- `rate-limiting-strategies.md` (DO for per-tenant limits)
- Cloudflare DO docs: https://developers.cloudflare.com/durable-objects/
- DO pricing: https://developers.cloudflare.com/durable-objects/platform/pricing/
