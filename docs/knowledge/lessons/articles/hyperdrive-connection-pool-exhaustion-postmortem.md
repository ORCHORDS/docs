# Hyperdrive Connection Pool Exhaustion Under Peak Load

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

During a flash-sale event, our checkout Worker began returning 500 errors. Logs showed:

```
Error: connect ETIMEDOUT — Hyperdrive pool exhausted; all connections in use.
```

Hyperdrive's connection pool to our PostgreSQL primary in `eu-west-1` was saturated.
New checkout requests queued behind the pool, exceeded their own 30-second timeout, and
returned errors to customers. Error rate peaked at 34 % of checkout attempts for 19 minutes.

## Context

Cloudflare Hyperdrive maintains a connection pool between Cloudflare's edge and your
database. Each Hyperdrive configuration has a maximum connection count (`max_connections`)
that defaults to 10 per Hyperdrive PoP. At our traffic peak we had 8 active PoPs routing
to the same Hyperdrive endpoint — effective maximum pool size was therefore 80 connections
across the edge — but our PostgreSQL `max_connections` was set to 50. Hyperdrive pooled
more aggressively than the database could accept, and the database refused new connections
when its own limit was breached, cascading errors back through Hyperdrive into the Worker.

There are two distinct limits at play that most operators conflate:

1. **Hyperdrive `max_connections`**: the number of connections each Cloudflare PoP's
   Hyperdrive pool will open to the database.
2. **PostgreSQL `max_connections`**: the hard server-side limit on simultaneous open
   connections regardless of source.

When `(hyperdrive_max_connections × active_PoPs) > postgres_max_connections`, the
database refuses new connections and Hyperdrive surfaces those refusals as pool errors.

---

## Timeline

| UTC | Event |
|-----|-------|
| 14:00 | Flash-sale email lands; traffic to checkout Worker × 12 baseline |
| 14:03 | First ETIMEDOUT errors in Worker logs |
| 14:06 | PagerDuty fires: checkout error rate 18 % |
| 14:09 | Database CPU normal; `pg_stat_activity` shows `max_connections` (50) fully consumed |
| 14:11 | On-call scales PostgreSQL connections via `ALTER SYSTEM SET max_connections = 150` + restart (causes 90-second downtime) |
| 14:22 | Errors clear; error rate returns to < 0.1 % |
| 14:41 | Incident closed; post-mortem scheduled |

---

## Why the Restart Made It Worse Before It Got Better

`ALTER SYSTEM SET max_connections` requires a PostgreSQL server restart to take effect.
The restart itself caused a 90-second connection-refused window, spiking errors further
before recovery. The correct emergency action was to reduce Worker fan-out by throttling
via a Durable Object rate limiter, buying time to restart the database during a lower-
traffic window. Instead we restarted under load.

---

## Fix: Right-size the Pool and Add a Back-Pressure Layer

**Step 1 — Calculate the correct `max_connections` before event traffic:**

```
postgres_max_connections ≥ (hyperdrive_max_connections × expected_active_PoPs) + 10
```

For us: `(10 × 8) + 10 = 90`. We set `max_connections = 120` to allow headroom.

**Step 2 — Configure Hyperdrive with an explicit pool size:**

```bash
# Update Hyperdrive config to cap connections per PoP
wrangler hyperdrive update <HYPERDRIVE_ID> \
  --max-connections=8 \
  --idle-connection-timeout=30
```

```toml
# wrangler.toml
[[hyperdrive]]
binding = "HYPERDRIVE"
id      = "<HYPERDRIVE_ID>"
# max_connections and idle_connection_timeout are set via wrangler CLI, not toml
```

**Step 3 — Add a Durable Object back-pressure gate in the checkout Worker:**

```typescript
// checkout-worker.ts — DB concurrency guard
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const gate = env.DB_GATE.get(env.DB_GATE.idFromName("global"));
    const permit = await gate.fetch(new Request("https://gate/acquire"));

    if (permit.status === 429) {
      return new Response(
        JSON.stringify({ error: "service_busy", retryAfter: 5 }),
        { status: 429, headers: { "Content-Type": "application/json", "Retry-After": "5" } }
      );
    }

    try {
      const result = await processCheckout(request, env);
      return result;
    } finally {
      await gate.fetch(new Request("https://gate/release"));
    }
  },
};
```

```typescript
// db-gate.ts — Durable Object limiting concurrent DB operations
export class DbGate implements DurableObject {
  private active = 0;
  private readonly MAX = 60; // stay below postgres max_connections

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/acquire") {
      if (this.active >= this.MAX) {
        return new Response("too many", { status: 429 });
      }
      this.active++;
      return new Response("ok");
    }

    if (url.pathname === "/release") {
      if (this.active > 0) this.active--;
      return new Response("ok");
    }

    return new Response("not found", { status: 404 });
  }
}
```

**Step 4 — Emit concurrency metrics to Analytics Engine for real-time visibility:**

```typescript
// Inside DbGate.fetch, after incrementing:
env.AE.writeDataPoint({
  blobs:   ["db_gate"],
  doubles: [this.active, this.MAX],
  indexes: ["db_concurrency"],
});
```

---

## Anti-patterns

- Setting PostgreSQL `max_connections` to a fixed value without modelling how many
  Hyperdrive PoPs could be active at peak traffic.
- Treating Hyperdrive as a limitless connection multiplexer — it pools connections but
  does not do back-pressure signalling to the Worker layer.
- Running `ALTER SYSTEM SET max_connections` + restart as the first emergency action
  during active traffic; the restart window compounds the incident.
- Not load testing at 3–10× expected peak before flash-sale events.

---

## Gotchas

- Hyperdrive's connection pool is per-PoP, not global. The Cloudflare dashboard shows
  aggregate metrics but `max_connections` applies per regional pool instance.
- `idle_connection_timeout` in Hyperdrive controls how long an idle pooled connection
  stays open. Reducing it frees database connections faster after a traffic spike but
  increases reconnect latency for subsequent requests.
- PostgreSQL's `pg_stat_activity` view is the ground truth for connection count; always
  query it during incidents rather than trusting Hyperdrive dashboard numbers alone.
- PgBouncer in front of PostgreSQL can decouple Hyperdrive's pool from the server's
  hard `max_connections` limit and is the recommended architecture for databases with
  > 3 Hyperdrive PoPs.

---

## Verification

Pre-event checklist:

1. `SELECT count(*) FROM pg_stat_activity` at 2× expected peak load test — must remain
   below `max_connections - 10`.
2. Durable Object gate metrics in Analytics Engine show no 429s during load test.
3. Hyperdrive dashboard shows stable latency histogram (no p99 spike) during load test.
4. `wrangler hyperdrive get <HYPERDRIVE_ID>` — verify `max_connections` and
   `idle_connection_timeout` match the capacity-planned values before every major event.

---

## Related

- `hyperdrive-connection-string-rotation-zero-downtime.md`
- `durable-objects-storage-quota-limit-incident.md`
- `connection-storms-on-failover-thundering-reconnects.md`
- `n-plus-one-queries-compound-at-scale.md`
- `queue-backlog-death-spirals.md`

---

## Sources

- Cloudflare Docs — Hyperdrive: https://developers.cloudflare.com/hyperdrive/
- Cloudflare Docs — Hyperdrive configuration: https://developers.cloudflare.com/hyperdrive/configuration/
- PostgreSQL Docs — `max_connections`: https://www.postgresql.org/docs/current/runtime-config-connection.html
- Internal incident ticket INC-2026-0359
- Internal load test report PERF-2026-Q2
