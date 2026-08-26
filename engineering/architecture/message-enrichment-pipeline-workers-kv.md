# Message Enrichment Pipeline with Workers KV Lookup

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project reaction events arrive in a Cloudflare Queue containing only `userId` and `postId`. Downstream consumers — notification Workers, analytics pipelines, moderation systems — each need the user's display name, the post's content hash, and the author's notification preferences. Without a shared enrichment step, every consumer independently queries D1 for the same data, inflating read costs and coupling every consumer to the DB schema.

## Context

The **message enrichment pattern** adds reference data to a thin event before it reaches specialised consumers, producing a **fat event** that is self-contained. In a Cloudflare Workers stack, the enrichment Worker sits between the raw event queue and the fan-out queue, performing KV lookups for hot reference data (user profiles, post metadata) and falling back to D1 for cache misses. This decouples consumers from the persistence layer, reduces D1 read pressure, and makes consumer code simpler. It is distinct from the Event-Carried State Transfer (ECST) pattern — ECST embeds state in domain events at *publish time*; message enrichment adds state *at consumption time* from an independent reference store.

## 1. Enrichment Pipeline Architecture

```
reactions-raw (Queue)
        │
        ▼
EnrichmentWorker
  ├── KV.get("user:{userId}")      ← hit: O(1), miss: D1 query + KV.put
  └── KV.get("post:{postId}")      ← same
        │ fat event
        ▼
reactions-enriched (Queue)
        │
        ├──▶ NotificationWorker
        ├──▶ AnalyticsWorker
        └──▶ ModerationWorker
```

A single enrichment step replaces N×M D1 reads (N consumers × M messages) with M KV lookups — mostly sub-millisecond reads from the same PoP.

## 2. Enrichment Worker Implementation

```typescript
interface ThinEvent {
  userId: string;
  postId: string;
  emoji: string;
  ts: number;
}

interface FatEvent extends ThinEvent {
  userDisplayName: string;
  userNotificationEnabled: boolean;
  postAuthorId: string;
  postContentHash: string;
}

export default {
  async queue(batch: MessageBatch<ThinEvent>, env: Env): Promise<void> {
    const enriched: FatEvent[] = [];

    for (const msg of batch.messages) {
      try {
        const fat = await enrich(msg.body, env);
        enriched.push(fat);
        msg.ack();
      } catch (err) {
        console.error('enrichment_failed', { id: msg.id, err: String(err) });
        msg.retry();
      }
    }

    // batch-send to the enriched queue for efficiency
    await env.REACTIONS_ENRICHED.sendBatch(
      enriched.map((body) => ({ body })),
    );
  },
};

async function enrich(event: ThinEvent, env: Env): Promise<FatEvent> {
  const [userMeta, postMeta] = await Promise.all([
    getUserMeta(event.userId, env),
    getPostMeta(event.postId, env),
  ]);
  return { ...event, ...userMeta, ...postMeta };
}
```

## 3. KV-First Reference Data Lookup with D1 Fallback

Keep KV as the hot cache and D1 as the source of truth. On a KV miss, hydrate from D1 and write back to KV with a TTL aligned to the expected staleness tolerance.

```typescript
interface UserMeta {
  userDisplayName: string;
  userNotificationEnabled: boolean;
}

async function getUserMeta(userId: string, env: Env): Promise<UserMeta> {
  const cached = await env.KV.get<UserMeta>(`user:${userId}`, 'json');
  if (cached) return cached;

  const row = await env.DB.prepare(
    'SELECT display_name, notification_enabled FROM user_profiles WHERE user_id = ?',
  )
    .bind(userId)
    .first<{ display_name: string; notification_enabled: number }>();

  if (!row) throw new Error(`user_not_found userId=${userId}`);

  const meta: UserMeta = {
    userDisplayName: row.display_name,
    userNotificationEnabled: row.notification_enabled === 1,
  };

  // TTL of 300 s — stale display name for 5 min is acceptable on example project
  await env.KV.put(`user:${userId}`, JSON.stringify(meta), { expirationTtl: 300 });
  return meta;
}

interface PostMeta {
  postAuthorId: string;
  postContentHash: string;
}

async function getPostMeta(postId: string, env: Env): Promise<PostMeta> {
  const cached = await env.KV.get<PostMeta>(`post:${postId}`, 'json');
  if (cached) return cached;

  const row = await env.DB.prepare(
    'SELECT author_id, content_hash FROM posts WHERE post_id = ?',
  )
    .bind(postId)
    .first<{ author_id: string; content_hash: string }>();

  if (!row) throw new Error(`post_not_found postId=${postId}`);

  const meta: PostMeta = {
    postAuthorId: row.author_id,
    postContentHash: row.content_hash,
  };

  // Posts are immutable after publication on example project; long TTL is safe
  await env.KV.put(`post:${postId}`, JSON.stringify(meta), { expirationTtl: 86400 });
  return meta;
}
```

## 4. Cache Invalidation on Reference Data Changes

When a user changes their display name, publish a cache invalidation event that the enrichment pipeline's KV entry reflects immediately rather than waiting for TTL expiry.

```typescript
// In the profile update Worker — after successful D1 write
async function invalidateEnrichmentCache(userId: string, env: Env): Promise<void> {
  await env.KV.delete(`user:${userId}`);
  // Optionally: publish an invalidation event to a separate queue
  // so any in-flight enrichments that just read stale data can be flagged
}
```

For post-mutation scenarios, couple the KV write to the enrichment store to the mutation transaction using the outbox pattern — write the invalidation event to D1 in the same batch as the profile update, then process it in a background Worker.

## 5. Partial Enrichment Tolerance

Not all enrichment failures should block delivery. Use a nullable fat event shape and let consumers decide how to handle missing fields, rather than retrying indefinitely on non-critical data.

```typescript
interface FatEventPartial extends ThinEvent {
  userDisplayName: string | null;
  userNotificationEnabled: boolean | null;
  postAuthorId: string | null;
  postContentHash: string | null;
  enrichmentError?: string;
}

async function enrichPartial(event: ThinEvent, env: Env): Promise<FatEventPartial> {
  const [userResult, postResult] = await Promise.allSettled([
    getUserMeta(event.userId, env),
    getPostMeta(event.postId, env),
  ]);

  return {
    ...event,
    userDisplayName: userResult.status === 'fulfilled' ? userResult.value.userDisplayName : null,
    userNotificationEnabled:
      userResult.status === 'fulfilled' ? userResult.value.userNotificationEnabled : null,
    postAuthorId: postResult.status === 'fulfilled' ? postResult.value.postAuthorId : null,
    postContentHash: postResult.status === 'fulfilled' ? postResult.value.postContentHash : null,
    enrichmentError:
      userResult.status === 'rejected' || postResult.status === 'rejected'
        ? 'partial_enrichment'
        : undefined,
  };
}
```

## Anti-patterns

- **Enriching inside each consumer Worker individually** — this is the problem the pattern solves; centralise enrichment in one Worker upstream of the fan-out queue.
- **Storing large blobs in KV enrichment cache** — KV values are limited to 25 MB but reads are billed per read, not per byte; store only the fields consumers actually need, not entire DB row dumps.
- **Using synchronous D1 calls without KV caching** — every D1 call under the enrichment Worker adds latency to the queue processing path; always check KV first.
- **Skipping `Promise.allSettled` for independent lookups** — two independent KV lookups should be parallelised with `Promise.all` or `Promise.allSettled`; sequential awaits double the latency.

## Gotchas

- KV read-after-write consistency is eventual within the same region but generally converges within 60 seconds globally. A cache invalidation written at the same PoP may not be visible to an enrichment Worker running at a distant PoP within that window — acceptable for display names, not acceptable for security-sensitive fields.
- `env.KV.get(key, 'json')` returns `null` on a cache miss (not an empty object); always check for `null` before using the result.
- `sendBatch()` on Cloudflare Queues has a maximum of 100 messages per call and a maximum payload size of 256 KB per message; chunk large enrichment batches before sending.
- The enrichment queue introduces one extra hop of delivery latency (~1–2 s); for reaction notifications where freshness matters, confirm this is acceptable with product stakeholders before adopting the pattern.

## Verification

1. Publish a thin reaction event; assert the enriched queue receives a fat event containing `userDisplayName` and `postAuthorId`.
2. Delete the KV entry for a user; publish a thin event; assert D1 is queried and KV is re-populated with the correct TTL.
3. Update a user's display name and call `invalidateEnrichmentCache`; publish a thin event for that user; assert the fat event contains the new display name.
4. Publish a thin event with a non-existent `postId`; assert the enrichment uses `Promise.allSettled` and the fat event carries `postAuthorId: null` and `enrichmentError: 'partial_enrichment'`.

## Related

- `event-carried-state-transfer-workers-kv.md`
- `event-carried-state-transfer.md`
- `caching-layers-cloudflare-workers-kv-d1.md`
- `pipeline-architecture-workers-queues-stages.md`
- `workers-queue-fanout-architecture.md`

## Sources

- Enterprise Integration Patterns — "Content Enricher" (Hohpe & Woolf): https://www.enterpriseintegrationpatterns.com/patterns/messaging/DataEnricher.html
- Cloudflare Workers KV documentation: https://developers.cloudflare.com/kv/
- Cloudflare Queues `sendBatch` limits: https://developers.cloudflare.com/queues/
