# Workers Returns 503 After Hitting the 50 Subrequest Limit Per Request

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker returns a 503 Service Unavailable response to the client even though the upstream services are healthy. The error appears intermittently under load or consistently when the Worker processes complex requests. Checking `wrangler tail` reveals log lines containing `Error: Too many subrequests` or a 503 status on outbound `fetch()` calls.

---

## Context

Cloudflare Workers enforce a hard limit of 50 subrequests per incoming request on the free and paid plans (the limit applies to `fetch()` calls, service-binding RPC calls, and calls to Durable Objects). When a Worker exhausts this budget, any subsequent outbound call throws or resolves with a 503. The limit exists to protect the Cloudflare network from runaway fan-out and to enforce predictable CPU/wall-clock usage. The limit resets for every new top-level incoming request; it is not a per-account rate limit. Workers that iterate over a list of items and call `fetch()` inside the loop are the most common trigger.

---

## Root Cause

The Worker calls `fetch()` (or a service binding) inside a sequential `for` loop, consuming one subrequest slot per iteration. When the list being iterated is longer than 50 items, the 51st call fails with 503, which is propagated back to the client.

```typescript
// BAD: sequential fetch inside a loop — burns one subrequest slot per item
export default {
  async fetch(request: Request): Promise<Response> {
    const ids: string[] = await getItemIds(request); // may return > 50 items

    const results: unknown[] = [];
    for (const id of ids) {
      // Each iteration consumes one of the 50 allowed subrequests
      const res = await fetch(`https://api.example.com/items/${id}`);
      if (!res.ok) {
        return new Response('upstream error', { status: 503 });
      }
      results.push(await res.json());
    }

    return Response.json(results);
  },
};
```

## Fix

Batch subrequests with `Promise.all()` to issue them concurrently, and chunk the list so that no single batch exceeds the remaining subrequest budget. Reserve a few slots for any bookkeeping requests (auth, logging, etc.).

```typescript
// GOOD: chunked concurrent fetches — stays within the 50-subrequest budget
const SUBREQUEST_LIMIT = 50;
const RESERVED_SLOTS = 5; // for auth, logging, etc.
const BATCH_SIZE = SUBREQUEST_LIMIT - RESERVED_SLOTS; // 45 per batch

async function fetchItem(id: string): Promise<unknown> {
  const res = await fetch(`https://api.example.com/items/${id}`);
  if (!res.ok) throw new Error(`upstream ${res.status} for id ${id}`);
  return res.json();
}

function chunk<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size));
  }
  return chunks;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const ids: string[] = await getItemIds(request);

    if (ids.length > BATCH_SIZE) {
      // For very large lists, consider moving to a Queue or Durable Object
      // and returning a 202 Accepted with a job ID instead.
      return new Response(
        JSON.stringify({ error: 'Request too large; use batch endpoint' }),
        { status: 413, headers: { 'Content-Type': 'application/json' } },
      );
    }

    const results = await Promise.all(ids.map(fetchItem));
    return Response.json(results);
  },
};
```

For lists that genuinely exceed 45 items, redesign the endpoint to accept batches from the client, or push work onto a **Queue** consumer that runs as a separate request (each message delivery resets the subrequest counter).

## Verification

```bash
# Stream live logs and filter for 503s coming from the Worker itself
npx wrangler tail my-worker --format pretty 2>&1 | grep -i '503\|subrequest'

# Send a test payload with exactly 46 IDs to confirm the old code fails
curl -s -o /dev/null -w '%{http_code}' \
  -X POST https://my-worker.example.workers.dev/batch \
  -H 'Content-Type: application/json' \
  -d '{"ids": ["1","2","3","4","5","6","7","8","9","10",
       "11","12","13","14","15","16","17","18","19","20",
       "21","22","23","24","25","26","27","28","29","30",
       "31","32","33","34","35","36","37","38","39","40",
       "41","42","43","44","45","46"]}'
# After fix, should return 413; before fix, returns 503

# Check subrequest usage in a test Worker with a counter (dev only)
npx wrangler dev --local
```

---

## Anti-patterns

- **Sequential `await fetch()` in a loop** — Each `await` consumes one subrequest slot and adds latency. Use `Promise.all()` to parallelize and reduce slot usage relative to wall time.
- **No guard on input list length** — Accepting arbitrary-length lists from clients without capping them means any payload larger than 50 items will 503 unconditionally.
- **Using service bindings as a workaround** — Calls to service bindings count against the same 50-subrequest budget. Switching from `fetch()` to a binding does not fix the root cause.
- **Ignoring the 503 in error handling** — Catching and retrying a 503 caused by the subrequest limit will never succeed within the same request; retrying wastes CPU and time.

---

## Gotchas

- The 50-subrequest limit applies per **top-level incoming request**, not per Worker invocation. A Durable Object stub call counts as one subrequest from the calling Worker's budget, even if the Durable Object itself makes zero outbound calls.
- `waitUntil()` tasks (background work) share the same subrequest budget as the main request handler. Background fan-out can silently exhaust the remaining slots.
- `Cache.put()` and `Cache.match()` do **not** count against the subrequest limit.
- Cloudflare's limit documentation rounds to 50; in practice, the platform may allow a few extra calls on paid plans, but relying on undocumented headroom is fragile.
- Workers AI binding calls count against the subrequest budget on some plan tiers.

---

## Related

- `workers-cron-missed-execution-recovery.md`
- `d1-query-timeout-full-table-scan.md`

---

## Sources

- Cloudflare Workers Limits — https://developers.cloudflare.com/workers/platform/limits/#subrequests
- Cloudflare Queues (offload fan-out) — https://developers.cloudflare.com/queues/
- Promise.all() MDN — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all
