# d1-global-read-replicas

Using D1 database read replicas to serve low-latency reads globally. D1
replicas let you read from geographically-distributed copies of your primary
database while all writes go to the primary. This is essential for apps with
global users where the primary is in one region.

## Symptom

Your D1-backed app is fast for users near the primary location (e.g., North
America), but users in Europe or Asia see **300-800ms read latency** because
every query crosses an ocean to the primary and back.

```text
User in EU → Worker (EU edge, 5ms) → D1 Primary (US-East, 120ms RTT)
Total: ~250ms for a simple SELECT
```

Writes are acceptably slow (users expect writes to take longer), but reads
dominate traffic (90%+ of queries) and feel sluggish globally.

## Background: D1 replication model

D1 databases have a **primary** (accepts reads + writes) and optional **read
replicas** (accept reads only). Replicas are asynchronously updated from the
primary — typically within 1-5 seconds, but NOT instantaneously.

```text
                    ┌─────────────┐
        Writes ───→ │   Primary   │ (single region)
                    │  (D1 main)  │
                    └──────┬──────┘
                           │ async replication (1-5s lag)
              ┌────────────┼────────────┐
              ↓            ↓            ↓
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Replica  │ │ Replica  │ │ Replica  │
        │  (EU)    │ │  (Asia)  │ │  (US-W)  │
        └──────────┘ └──────────┘ └──────────┘
              ↑            ↑            ↑
     EU reads       Asia reads    US-W reads
```

## Solution: Route reads to nearest replica

### Step 1: Enable replicas

```bash
# Create read replicas in target regions
npx wrangler d1 create-replica my-db --location=weur   # Western Europe
npx wrangler d1 create-replica my-db --location=apac   # Asia Pacific
npx wrangler d1 create-replica my-db --location=wnam   # Western North America
```

### Step 2: Configure wrangler.toml

```toml
[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
# D1 automatically routes reads to the nearest replica when
# using the default binding. No special config needed for basic geo-routing.
```

### Step 3: Read/write routing in code

```typescript
interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const method = request.method;

    if (url.pathname.startsWith("/api/")) {
      if (method === "GET") {
        // Reads automatically use nearest replica (sub-50ms globally)
        const results = await env.DB.prepare(
          "SELECT * FROM posts WHERE published = 1 ORDER BY created_at DESC LIMIT 20"
        ).all();
        return Response.json(results.results);
      } else {
        // Writes go to primary
        const body = await request.json();
        await env.DB.prepare(
          "INSERT INTO posts (title, content, author_id) VALUES (?, ?, ?)"
        ).bind(body.title, body.content, body.authorId).run();
        return Response.json({ success: true });
      }
    }

    return new Response("Not found", { status: 404 });
  },
};
```

### Step 4: Explicit session consistency for read-after-write

After a user writes, they expect to immediately see their change. But if the
read goes to a replica with 3s lag, the user sees stale data.

```typescript
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/posts" && request.method === "POST") {
      // Write to primary
      const result = await env.DB.prepare(
        "INSERT INTO posts (title, content) VALUES (?, ?) RETURNING *"
      ).bind("My Post", "Content").first();

      // DON'T immediately read from replica — it may not have the write yet.
      // Option A: Return the write result directly (no second query needed)
      return Response.json(result);

      // Option B: If you must query, force read from primary by using a
      // write-then-read pattern within the same request (D1 serializes
      // same-request reads after writes to the primary automatically).
    }
  },
};
```

## When to use replicas vs. when NOT to

### Use replicas when:
- Read-heavy workload (>80% reads)
- Global user base across 2+ continents
- Tolerance for 1-5 second staleness on reads
- Analytics/dashboard queries where freshness isn't critical

### Do NOT use replicas when:
- **Single-region app.** If all users are in one country, the primary alone
  is faster — replicas add complexity with zero benefit.
- **Strong consistency required.** Financial transactions, inventory counts,
  booking systems where stale reads cause real problems. Use the primary for
  these queries.
- **Write-heavy workload.** Replicas don't help writes at all — all writes
  still hit the single primary. If writes are your bottleneck, replicas
  won't fix it; you need Durable Objects or sharding.

## Gotchas

- **Replication lag is real and variable.** It's usually 1-5 seconds but can
  spike to 10-15s under heavy write load. Never assume a replica reflects
  the latest write. Build your UI to handle this (optimistic updates, or
  return write results directly without re-querying).
- **Replicas are read-only.** Any `INSERT`, `UPDATE`, `DELETE`, or DDL
  (`CREATE TABLE`, `ALTER`) automatically routes to the primary. But if
  you're using a transaction with mixed read/write, the entire transaction
  goes to the primary — you lose replica benefits for that transaction.
- **Replicas cost money.** Each replica is billed as a separate D1 database
  for storage + rows read. 3 replicas = 4x storage cost (1 primary + 3
  replicas). Monitor your bill.
- **Schema migrations apply to primary first.** When you run a migration,
  it hits the primary immediately. Replicas catch up asynchronously. During
  the lag window, replicas have the old schema and primary has the new one.
  If your app queries a replica with a column that doesn't exist there yet,
  you get an error. **Deploy schema changes in backward-compatible stages.**
- **`wrangler d1 execute` hits the primary by default.** Don't use it to
  test replica behavior. Use actual HTTP requests through your Worker.
- **Connection pooling is different.** D1 uses HTTP-based sessions, not
  persistent TCP connections, so traditional connection pooling concerns
  don't apply. But each `.prepare()` is a fresh statement — reuse prepared
  statement patterns for cache efficiency.
- **The `cf` property on `Request` can tell you the colo.** Use it to
  debug which replica is being used:

```typescript
const colo = request.cf?.colo as string; // e.g., "FRA" = Frankfurt
console.log(`Serving from ${colo}`);
```

- **Failover is automatic but not instant.** If the primary goes down, D1
  promotes a replica. This takes 30-60 seconds. During failover, writes fail.
  Design your app to retry writes with exponential backoff.

## Cost comparison

| Setup                  | Monthly base | Latency (EU user, read) |
|------------------------|-------------|------------------------|
| Primary only (US-East) | $0.75/mo    | ~250ms                 |
| Primary + 1 EU replica | ~$1.50/mo   | ~25ms                  |
| Primary + 3 replicas   | ~$3.00/mo   | ~25ms globally         |

For a global SaaS, the 10x latency improvement for $2.25/mo extra is a clear win.
For a local business app, it's wasted money.
