# CQRS on Cloudflare Workers with D1 and KV/R2 Projections

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Anonymous social platforms under read-heavy mobile traffic collapse when a single D1 Worker handles both mutations (post creation, reaction events, follow graph writes) and fan-out reads (feed rendering, profile aggregations). D1's per-database query throughput limit surfaces as 429s on read paths under sustained bursts even when write volume is low.

## Context

example project (example.com) runs on Cloudflare Pages + Workers with D1 as the authoritative store. Mobile clients hit the read path ten to twenty times more often than the write path. CQRS — Command Query Responsibility Segregation — solves this by routing all state-changing commands to a dedicated Write Worker backed by D1, while a separate Read Worker serves pre-materialised projections stored in KV or R2. The two Workers share no request lifecycle; eventual consistency is an explicit design choice, not an accident.

## Write Worker Design

The Write Worker owns every mutation: creating posts, recording reactions, updating follow relationships, and expiring ephemeral content. It validates commands, writes to D1 inside a transaction where atomicity matters, then enqueues a projection-rebuild task via Workers Queue.

```typescript
// write-worker/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cmd = await request.json<WriteCommand>();

    switch (cmd.type) {
      case 'POST_CREATE': {
        const id = crypto.randomUUID();
        await env.DB.prepare(
          'INSERT INTO posts (id, author_hash, body, created_at) VALUES (?,?,?,?)'
        ).bind(id, cmd.authorHash, cmd.body, Date.now()).run();

        // Signal the projection builder
        await env.PROJECTION_QUEUE.send({ event: 'post.created', id, authorHash: cmd.authorHash });
        return Response.json({ id }, { status: 201 });
      }

      case 'REACTION_TOGGLE': {
        await env.DB.batch([
          env.DB.prepare(
            'INSERT OR IGNORE INTO reactions (post_id, reactor_hash, emoji) VALUES (?,?,?)'
          ).bind(cmd.postId, cmd.reactorHash, cmd.emoji),
          env.DB.prepare(
            'UPDATE posts SET reaction_count = reaction_count + 1 WHERE id = ?'
          ).bind(cmd.postId),
        ]);
        await env.PROJECTION_QUEUE.send({ event: 'reaction.toggled', postId: cmd.postId });
        return new Response(null, { status: 204 });
      }
    }
  },
};
```

## Read Worker Design

The Read Worker never touches D1. It reads KV projections written by the Queue consumer. Cache misses return stale data from R2 (a richer secondary store) rather than hitting D1.

```typescript
// read-worker/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const feedKey = `feed:${url.searchParams.get('cursor') ?? 'latest'}`;

    // L1: KV — hot feed tiles, TTL 30 s
    let raw = await env.KV.get(feedKey, 'text');

    if (!raw) {
      // L2: R2 — full projection JSON, no TTL
      const obj = await env.FEED_BUCKET.get(`projections/${feedKey}.json`);
      raw = obj ? await obj.text() : null;
      if (raw) await env.KV.put(feedKey, raw, { expirationTtl: 30 });
    }

    if (!raw) return Response.json({ items: [], stale: true }, { status: 200 });

    const headers = new Headers({ 'Content-Type': 'application/json' });
    headers.set('Cache-Control', 'public, max-age=15, stale-while-revalidate=45');
    return new Response(raw, { headers });
  },
};
```

## Projection Builder (Queue Consumer)

The Queue consumer rebuilds KV/R2 projections asynchronously after every write event. It runs in a separate Worker bound to the same Queue.

```typescript
// projection-worker/src/index.ts
export default {
  async queue(batch: MessageBatch, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const ev = msg.body as ProjectionEvent;

      if (ev.event === 'post.created') {
        const feed = await rebuildLatestFeed(env.DB, 50);
        const json = JSON.stringify(feed);
        await env.FEED_BUCKET.put(`projections/feed:latest.json`, json);
        await env.KV.put('feed:latest', json, { expirationTtl: 30 });
      }

      if (ev.event === 'reaction.toggled') {
        const post = await rebuildPostProjection(env.DB, ev.postId!);
        await env.KV.put(`post:${ev.postId}`, JSON.stringify(post), { expirationTtl: 60 });
      }

      msg.ack();
    }
  },
};
```

## Eventual Consistency Window

```
Write Worker ──► D1 (authoritative) ──► Queue ──► Projection Worker ──► KV / R2
    │                                                                        │
    │  <─────────────── typical lag: 200 ms – 2 s ────────────────────────> │
```

| Scenario                        | Consistency window | User-visible impact           |
|---------------------------------|--------------------|-------------------------------|
| Reaction count after toggle     | 200 ms – 1 s       | Counter lags one refresh      |
| New post appearing in feed      | 0.5 s – 2 s        | Post missing one pull-to-refresh |
| Follow count on profile         | 1 s – 5 s          | Stale count on first open     |
| Deleted post still visible      | Up to 30 s (KV TTL)| Ghost card before eviction    |

## Mobile Read Latency Optimisation

Mobile clients on example project send a `X-Device-Hint: mobile` header. The Read Worker splits its KV key space by device tier, stores a stripped projection (no full body, no high-res URLs) under the `mobile:` prefix, and returns it with a longer max-age to offset lossy connections.

```typescript
const isMobile = request.headers.get('X-Device-Hint') === 'mobile';
const prefix = isMobile ? 'mobile' : 'web';
const feedKey = `${prefix}:feed:latest`;
const maxAge = isMobile ? 45 : 15;
```

Mobile projection strips:
- Full post body → trimmed to 280 chars
- Video URLs → thumbnail-only URL
- Reaction breakdown → total count only

## Anti-patterns

- **Bypassing the Read Worker for "just one field"** — any D1 query from a hot read path re-introduces the throughput ceiling the pattern is designed to avoid.
- **Synchronous projection rebuild in the Write Worker** — blocks the write response, wastes D1 read capacity, and couples two bounded contexts.
- **Shared D1 binding in both Workers** — defeats isolation; the Read Worker must have no DB binding.
- **Single KV namespace for read and system keys** — key collisions are silent; namespace per concern.
- **Not acknowledging Queue messages on projection success** — the Queue retries indefinitely, causing duplicate projection writes and KV thrashing.

## Gotchas

- D1 batches are atomic per batch call but sequential across batch calls in the same request; do not assume cross-batch atomicity.
- Workers Queue delivers at-least-once; projection rebuilds must be idempotent (overwrite, not append).
- KV `expirationTtl` minimum is 60 seconds on Cloudflare's free tier; on paid plans the minimum is 1 second.
- R2 `put` is eventually consistent within a region but not globally instantaneous; a freshly written object may 404 for up to 2 seconds on first read from a distant PoP.
- `crypto.randomUUID()` is available in Workers runtime without any import.

## Verification

```bash
# Confirm Write Worker responds and enqueues
curl -X POST https://write.example.com/commands \
  -H 'Content-Type: application/json' \
  -d '{"type":"POST_CREATE","authorHash":"abc123","body":"hello example project"}'
# Expect: 201 {"id":"<uuid>"}

# Wait ~1 s then poll Read Worker
curl https://read.example.com/feed?cursor=latest
# Expect: 200 with items[] containing the new post

# Confirm KV projection key exists
wrangler kv key get --namespace-id=<NS_ID> "feed:latest"
```

## Related

- `caching-layers-cloudflare-workers-kv-r2.md`
- `workers-queue-fanout-architecture.md`
- `cqrs-pattern.md`
- `event-sourcing-projections-snapshots.md`
- `read-write-splitting-topology.md`

## Sources

- Cloudflare D1 documentation — database limits and batch semantics
- Cloudflare Workers Queue documentation — at-least-once delivery guarantees
- Martin Fowler, "CQRS" (martinfowler.com/bliki/CQRS.html)
- Greg Young, CQRS Documents (cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf)
