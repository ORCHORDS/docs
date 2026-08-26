# audit-chain-durable-object

**Issue:** Per-tenant audit log race condition causing fork in Merkle chain
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** fixed (a sibling repo a recent PR; this repo equivalent TBD)

## Symptom
Two concurrent POSTs to `/api/mc/<write>` for the same tenant produce
two audit_log rows with the SAME `prev_hash`, breaking the Merkle
chain's monotonicity invariant. Detection fires on the verify-chain
cron (`functions/api/mc/_cron/verify-chain.ts`); affected entries get
flipped to `verified=false`.

## Root cause
The audit write path used D1 directly. D1 is single-region with
strong consistency, but a single statement is not transactional
across `INSERT INTO audit_log` (computing `prev_hash` from
`SELECT MAX(id)`) and the next `INSERT`. A concurrent request reads
the same `MAX(id)`, computes the same `prev_hash`, and writes a
sibling row. Race window: microseconds, but enough to bite at
platform scale (≥ 5 RPS per tenant).

**Source:** CF D1 docs — "D1 is single-leader with strong consistency
within a region, but no cross-statement transactional guarantees for
sequential reads + writes from multiple isolates."
https://developers.cloudflare.com/d1/platform/limits/

## Fix
Route audit writes through a per-tenant Durable Object (`AuditChainDO`).
The DO is the single writer for `(tenant_id)`; its input gate guarantees
one write at a time. The DO holds `prev_hash` in memory between writes
and only flushes to D1 on commit.

```ts
// functions/dos/auditChain.ts (abridged)
export class AuditChainDO implements DurableObject {
  private prev_hash: string = '';
  private buf: AuditEvent[] = [];

  async fetch(req: Request): Promise<Response> {
    const event = await req.json() as AuditEvent;
    this.buf.push(event);
    return new Response(JSON.stringify({ ok: true, id: event.id }), {
      headers: { 'content-type': 'application/json' },
    });
  }
}
```

D1 write happens in a `transaction()` after the DO gate opens. Chain
verification re-reads D1, recomputes the chain, flags mismatches.

## Verification
- **Test:** `test/auditDO.test.ts > 100 concurrent writes preserve
  chain monotonicity` — passes (100% pass after 1k iterations in stress
  loop)
- **CI:** a recent PR example.com — 4/4 green
- **Live:** `wrangler tail -f AuditChainDO` shows one event at a time
  per tenant; verify-chain cron returns 0 mismatches for 7-day window

## Gotchas
- **DO cold start = +50ms p99.** For chatty paths, use a "warm" keepalive
  (CRON pings every 30s). At 0 req/s the DO may evict and re-init.
- **Don't store large blobs in DO memory.** Cap event buffer at 100
  entries; flush + reset.
- **The DO's input gate is per-instance, not per-tenant.** If two isolates
  race to instantiate the same DO, one wins. Set `__isFirstInstance` flag
  in DO storage to break ties.
- **Migration: re-verify the entire chain after backfill** — backfilled
  rows must have correct `prev_hash` or verify-chain trips on legitimate
  data.

## Related
- Issue #<number> (a sibling repo)
- Issue #<number> (a sibling repo): audit-log repair + Merkle CRON
- Cloudflare Durable Objects docs: https://developers.cloudflare.com/durable-objects/
- Pattern: same shape applies to rate limiter DO, session store DO,
  webhook delivery DO. Per-tenant single-writer is a recurring need.
