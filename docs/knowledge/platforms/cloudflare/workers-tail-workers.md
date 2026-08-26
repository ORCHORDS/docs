# workers-tail-workers

**Issue:** Attaching a Tail Worker to observe live execution traces of another Worker
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tail Workers receive a stream of `TailEvent` objects for every request handled by a "producer" Worker. They are ideal for real-time logging, error alerting, and observability without modifying the producer code.

## Pattern / Solution

```toml
# wrangler.toml for the TAIL worker
name = "my-tail-worker"
main = "src/tail.ts"
```

```typescript
// src/tail.ts — the Tail Worker
export default {
  async tail(events: TraceItem[], env: Env, ctx: ExecutionContext): Promise<void> {
    for (const event of events) {
      // event.scriptName — which Worker this trace is from
      // event.outcome   — 'ok' | 'exception' | 'exceeded-cpu' | 'canceled' | 'unknown'
      // event.logs      — console.log() output from the producer
      // event.exceptions — uncaught errors

      if (event.outcome !== 'ok') {
        ctx.waitUntil(alertSlack(event, env));
      }

      ctx.waitUntil(
        env.ANALYTICS.writeDataPoint({
          indexes: [event.scriptName ?? 'unknown'],
          blobs: [event.outcome, event.exceptions[0]?.message ?? ''],
          doubles: [event.cpuTime ?? 0, event.wallTime ?? 0],
        })
      );
    }
  },
};

async function alertSlack(event: TraceItem, env: Env): Promise<void> {
  await fetch(env.SLACK_WEBHOOK, {
    method: 'POST',
    body: JSON.stringify({
      text: `Worker *${event.scriptName}* failed: \`${event.outcome}\`\n${
        event.exceptions.map(e => e.message).join('\n')
      }`,
    }),
    headers: { 'Content-Type': 'application/json' },
  });
}
```

**Attaching the Tail Worker (Dashboard):**
1. Go to Workers → producer Worker → Settings → Observability.
2. Under "Tail Workers", select your tail Worker.
3. Save. Changes take effect immediately.

**Or via `wrangler.toml` of the producer:**
```toml
# Producer's wrangler.toml
[observability]
enabled = true

[[tail_consumers]]
service = "my-tail-worker"
```

## Gotchas
- Tail Workers receive events **after** the response is sent; they cannot modify the response.
- A Tail Worker **cannot** attach its own Tail Worker (no recursive tailing).
- Tail events are sampled at 100% by default for paid plans; on free plans they may be sampled.
- `event.logs` contains only `console.log` / `console.error` output, not arbitrary data.
- CPU and wall time in tail events are approximate and not billable-grade metrics.
- Tail Workers themselves have a 10 ms CPU budget — keep logic minimal and use `waitUntil` for heavier work.
- The `tail` export is a top-level handler separate from `fetch`.

## Related
- `workers-logpush.md`
- `workers-analytics-engine.md`
- `workers-best-practices.md`
