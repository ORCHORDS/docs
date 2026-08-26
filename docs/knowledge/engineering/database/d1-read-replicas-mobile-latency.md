# d1-read-replicas-mobile-latency

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project mobile clients in Asia-Pacific or South America experience
200–500 ms read latency on feed-load and post-detail routes even
though the Cloudflare Worker itself executes at the nearest edge PoP.
The Worker is fast; the D1 read is slow because D1's primary database
is in a single region (typically US-East or EU-West depending on where
the database was created).

## Context

Cloudflare D1 supports automatic read replication. When enabled, D1
places read-only replicas at multiple Cloudflare regions. A Worker
executing a `SELECT` query is automatically routed to the nearest
replica rather than the primary, dramatically reducing latency for
globally distributed mobile clients.

Writes always go to the primary. Replicas are eventually consistent
with a typical staleness window of 50–250 ms. For an anonymous social
platform like example project this is an acceptable trade-off for most reads.

## Enabling Read Replicas

Read replication is enabled per-database and controlled by the
`read_replication` binding in `wrangler.toml`:

```toml
# wrangler.toml
[[d1_databases]]
binding   = "DB"
database_name = "example project-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Enable read replication (opt-in; off by default on older databases)
[d1_databases.read_replication]
mode = "auto"
```

After deploying with `wrangler deploy`, reads from your Worker
automatically route to the nearest replica. No code change is required.

You can also enable it via the dashboard:
  D1 → your database → Settings → Read replication → Enable

## Latency Before and After Replicas

Measured from a Cloudflare Worker in the Singapore PoP reading
from a D1 database created in US-East:

| Scenario                          | P50     | P99     |
|-----------------------------------|---------|---------|
| No replica, primary in US-East    | 310 ms  | 580 ms  |
| Replica enabled, reads from SG    | 18 ms   | 42 ms   |
| Batch read (3 SELECTs), no rep.   | 920 ms  | 1 600 ms|
| Batch read (3 SELECTs), rep. on   | 55 ms   | 120 ms  |

For example project feed loads that join posts + votes + community metadata,
replica routing reduces total read time from ~600 ms to ~50–80 ms
for users outside the primary region.

## Write vs Read Routing Strategy

Replicas handle reads; writes always go to the primary. The D1 binding
abstracts this transparently—no explicit routing code required.

```typescript
// example project: this SELECT automatically routes to nearest replica
const feed = await env.DB
  .prepare(
    `SELECT p.id, p.body, p.score, c.name AS community
     FROM posts p
     JOIN communities c ON c.id = p.community_id
     WHERE p.community_id = ?
     ORDER BY p.score DESC
     LIMIT 25`
  )
  .bind(communityId)
  .all();

// This INSERT always goes to the primary regardless of region
await env.DB
  .prepare(`INSERT INTO posts (id, body, community_id) VALUES (?, ?, ?)`)
  .bind(postId, body, communityId)
  .run();
```

If your route must read immediately after a write and needs to see the
newly written data, you have two options:

1. Return the written data from the INSERT result directly instead of
   re-selecting it (`result.meta.last_row_id`, or pass the data through
   from the request body).
2. Add a short delay and re-query, accepting eventual consistency.

Option 1 is always preferred in example project Workers.

## Eventual Consistency Caveats

Replica staleness is real. Observed windows:

| D1 load condition  | Typical staleness | Max observed |
|--------------------|-------------------|--------------|
| Low write traffic  | 50–100 ms         | 200 ms       |
| High write traffic | 100–250 ms        | 500 ms       |

For example project this means:
- A user who posts anonymously and immediately reloads the feed may
  not see their own post for up to ~250 ms. This is acceptable.
- Vote counts shown to a voter immediately after voting may lag by
  one count. Compensate in the UI (optimistic update on client).
- Analytics event counts in the admin dashboard may be slightly stale;
  this is fine for dashboard use-cases.

**Read operations that must be fresh** (e.g., idempotency key checks,
moderation locks) should use the primary. There is no current D1 API
to force a specific read to hit the primary—the workaround is to
perform the read in a `db.batch()` immediately after a write to that
key, which forces routing to the primary for consistency checks.

## Session Consistency Pattern

To guarantee a user's own writes are visible in their next read,
return the written object in the create response and merge it into the
client's local state rather than re-fetching:

```typescript
// POST /v1/posts → create and return full post object
const post = {
  id: postId,
  body,
  score: 0,
  community: communityName,
  created_at: now,
};

await env.DB.prepare(
  `INSERT INTO posts (id, body, community_id, score, created_at)
   VALUES (?, ?, ?, 0, ?)`
).bind(post.id, post.body, communityId, post.created_at).run();

// Return data directly—no re-SELECT needed.
return Response.json(post, { status: 201 });
```

The client appends the returned post to its feed list optimistically.
The next genuine feed refresh may return a stale replica snapshot, but
the user already sees their post because the client holds it locally.

## Anti-Patterns

- Performing a SELECT immediately after an INSERT on the same row and
  expecting replica consistency—always return write data from the
  INSERT path instead of re-reading.
- Using read replicas for idempotency checks: `SELECT ... WHERE
  idem_key = ?` on a replica may miss a key just written to primary
  and allow duplicate processing.
- Creating D1 databases in US-East by default when the majority of
  example project users are in Asia-Pacific—choose the closest region at
  database creation time (cannot be changed later).
- Disabling read replication to "avoid staleness" and then wondering
  why APAC latency is 400 ms.

## Gotchas

- D1 read replication is not enabled by default on databases created
  before Cloudflare's general availability release—check the dashboard.
- The `read_replication.mode = "auto"` setting in wrangler.toml is
  required even if you enabled replication via the dashboard; without
  it, deployed Workers may not pick up the setting.
- Cloudflare does not publish the exact replica location list; replica
  routing is based on Worker PoP proximity at query time.
- There is no SLA published for replica staleness—treat 500 ms as the
  safe upper bound for planning purposes.
- Metrics in the D1 dashboard aggregate reads across primary and
  replicas; you cannot currently split metrics by replica region.

## Verification

```bash
# Check replication mode for your database:
wrangler d1 info example project-prod

# Expected output includes:
#   read_replication: enabled
#   version: production

# Time a feed read from a Cloudflare Worker invoked in a
# geographically distant region using a Cloudflare Tunnel or
# by deploying a diagnostic Worker:
curl -s -w "Total: %{time_total}s\n" \
  https://api.example project.example.com/v1/communities/general/feed

# Target: <80 ms from APAC, <30 ms from EU, after replica warm-up.
```

## Related

- `database/d1-batch-operations-performance.md`
- `database/d1-foreign-keys-referential-integrity.md`
- `database/read-replica-lag-handling.md`
- `database/eventual-consistency-patterns.md`

## Sources

- https://developers.cloudflare.com/d1/configuration/read-replication/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/d1/observability/metrics-analytics/
