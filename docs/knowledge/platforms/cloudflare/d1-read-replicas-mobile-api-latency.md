# D1 Global Read Replicas: Mobile API Latency

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A mobile user in Sydney or Singapore taps a feed action.
The GET response takes ~1.8 s. The trace shows the D1
query alone consuming 1.6 s — no N+1 problem, no missing
index. The Worker is crossing an ocean to the US primary
on every read. Desktop users near the primary notice
nothing; mobile users in APAC or OC pay the full RTT
penalty on every request.

example project has 133+ Worker routes, a global mobile user
base, and D1 as the primary datastore. Read traffic is
roughly 90% of all query volume.

## Context

D1 global read replication entered public beta in April
2025. When enabled (`read_replication: {mode: "auto"}`),
D1 auto-provisions read-only replicas in six regions:

  ENAM, WNAM, WEUR, EEUR, APAC, OC

Replicas are free — billing stays rows_read/rows_written
regardless of which instance serves a query. Writes
always route to the single primary (region fixed at DB
creation). **Enabling replicas without the Sessions API
produces zero latency improvement** — the plain
`env.DB.prepare()` path bypasses replica routing.

## How D1 Distributed Reads Work

The D1 routing layer sits between the Worker binding and
the Durable Object instances. For each query it checks:
(1) query type (read vs. write), (2) session bookmark,
(3) replica availability and lag. Reads are sent to the
nearest instance that satisfies the bookmark constraint.

```
Mobile (SYD) → Worker (OC edge)
  ├─ SELECT → routing layer → OC replica  (~5 ms)
  └─ INSERT → routing layer → primary US  (~180 ms)
```

If the nearest replica lags behind the session bookmark,
the routing layer falls back to primary automatically.
Observability: `result.meta.served_by_region` (e.g.
`"OC"`) and `result.meta.served_by_primary` (bool).

## Write-Path Latency and Replication Lag

All writes commit at the primary. Async replication
propagates them to region replicas afterwards.

```
Region pair       Typical confirm lag
ENAM → WNAM       ~45 ms
ENAM → WEUR       ~55 ms
WNAM → WEUR/EEUR  ~75 ms
ENAM/WNAM → APAC  ~150 ms
ENAM/WNAM → OC    ~180-200 ms
```

Lag is bounded by the speed of light. A mobile write
from Sydney goes to the US primary (~180 ms RTT) — this
is unavoidable without relocating the primary at DB
creation time.

## Sessions API and Bookmarks

Bookmarks are Lamport timestamps (monotone increasing).
Each write produces a new bookmark. Passing a bookmark
to `withSession()` guarantees the serving instance has
applied every commit up to that point.

| Init value             | First query routes to      |
|------------------------|----------------------------|
| `"first-unconstrained"`| nearest instance (fastest) |
| `"first-primary"`      | primary (always fresh)     |
| `<bookmark string>`    | any instance >= bookmark   |

Per-request pattern (one session per handler call):

```typescript
export default {
  async fetch(req: Request, env: Env) {
    const bm = req.headers.get("x-d1-bookmark")
               ?? "first-unconstrained";
    const session = env.DB.withSession(bm);

    // Reads → nearest replica while session unpinned
    const rows = await session
      .prepare("SELECT * FROM feed LIMIT 20")
      .all();

    // First write pins session to primary for this req
    // await session.prepare("INSERT ...").run();

    const res = Response.json(rows.results);
    const next = session.getBookmark();
    if (next) res.headers.set("x-d1-bookmark", next);
    return res;
  }
};
```

The client (iOS / Android) stores the bookmark and
echoes it on every call. Any of the 133+ Worker routes
that accept it will honour the same consistency point —
the guarantee is per-database-state, not per-server.

## Latency Impact on Global Mobile Users

Real-world benchmark: primary in WEUR (London), user
in Oceania, measuring the D1 read portion of the
response (source: jackpearce.co.uk, April 2025).

```
Scenario             p50 read   p95
No replicas          ~1,800 ms  >2 s
Replicas + sessions    ~78 ms  ~120 ms
Improvement            95.7%
```

The 78 ms figure is the OC Worker → OC replica round
trip (local, < 5 ms each way) plus query execution. The
pre-replication number was the OC Worker → WEUR primary
transoceanic RTT.

## Smart Placement Interaction

Smart Placement moves a Worker near its backend — by
default this means near the D1 primary. For write-heavy
Workers that is correct. For read-heavy global Workers
it conflicts with replica benefit:

```
Smart Placement ON, replicas enabled
  Worker: co-located with primary (US-East)
  Mobile SYD user: ~200 ms edge-to-Worker
  D1 read: primary, 5 ms (local) — replica unused

Smart Placement OFF, replicas enabled
  Worker: OC edge (near user)
  D1 read: OC replica, 5 ms (local) — fast
  D1 write: OC Worker → US primary, ~180 ms
```

Recommended per-route split for example project:

| Route type           | Smart Placement |
|----------------------|-----------------|
| GET /feed, /profile  | OFF             |
| POST /payment/order  | ON              |
| Mixed CRUD (< 20%    | OFF + sessions  |
|   write by volume)   |                 |

Placement is set in wrangler.toml per Worker. Omitting
the `[placement]` block keeps the default (user-edge).

## Anti-patterns

- **`env.DB.prepare()` on any route after enabling
  replicas.** Always hits the primary. Replicas idle.
  Migrate all 133 routes to `withSession`.

- **`"first-primary"` on read-only endpoints.** Forces
  every session opener to the primary. Reserve it for
  write paths the client has no bookmark for yet.

- **One session shared across concurrent requests.**
  Sessions carry per-request state (bookmark, pin).
  Sharing across isolate re-uses causes bookmark drift
  and routing errors. Instantiate per-handler call.

- **Replicas on payment or inventory state.** Stale
  inventory counts cause over-selling. Use
  `"first-primary"` sessions or bypass Sessions API
  entirely on these paths and call the primary binding.

- **Smart Placement ON for read-heavy global routes.**
  Moves Worker to primary region; negates replica reads.

## Gotchas

- Under heavy write load, replica lag can spike to
  ~350 ms. D1 falls back to primary automatically, but
  `result.meta.served_by_primary` becomes `true`. Log
  this to detect unexpected primary fallback at scale.

- Schema migrations reach the primary immediately and
  replicas asynchronously. A new NOT NULL column can
  produce errors on replica reads during the lag window.
  Use nullable additions; never add NOT NULL columns in
  the same migration that populates them.

- `session.getBookmark()` returns `null` before any
  query executes. Guard: `session.getBookmark() ?? ""`.

- Disabling replication takes up to 24 h for replicas
  to drain. For incident response use `"first-primary"`
  as the fast mitigation, not a dashboard disable.

## Verification

```bash
# Enable via REST API
curl -X PATCH \
  "https://api.cloudflare.com/client/v4/accounts/\
$ACCT/d1/database/$DB_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"read_replication":{"mode":"auto"}}'

# Confirm replica serving from a remote host (AU/SG)
# Add header in Worker: res.headers.set("x-db-region",
#   result.meta.served_by_region ?? "primary")
curl -sI https://api.example.com/feed | grep x-db-region
# Expected: x-db-region: OC

# p50 before / after from AU VPS
ab -n 100 -c 5 https://api.example.com/feed | grep "50%"
```

Assert `served_by_primary` is `false` on GET endpoints.
If `true`, a stray write or `"first-primary"` is pinning
the session — trace the handler for the offending call.

## Related

- `cloudflare/d1-sessions-api.md` — Sessions API
  internals, pinning, and transaction semantics
- `cloudflare/d1-global-read-replicas.md` — manual
  provisioning and cost model
- `cloudflare/smart-placement-best-practices.md` —
  Smart Placement config and disabling per-Worker
- `cloudflare/http3-quic-mobile-network-irregularities.md`
  — last-mile mobile latency below the DB layer
- `cloudflare/workers-best-practices.md` — binding
  and wrangler.toml configuration reference

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/d1/best-practices/read-replication/
- https://blog.cloudflare.com/d1-read-replication-beta/
- https://developers.cloudflare.com/changelog/post/2025-04-10-d1-read-replication-beta/
- https://www.jackpearce.co.uk/posts/improving-api-response-times-using-d1-global-read-replication/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developers.cloudflare.com/workers/configuration/smart-placement/
