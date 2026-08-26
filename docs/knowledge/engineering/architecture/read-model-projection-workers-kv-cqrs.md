# Read Model Projection with Workers KV — CQRS Read Side

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your write side stores normalised domain events in D1 but every read query
joins four tables, recalculates aggregates, and still misses the sub-10 ms
latency SLA. You need pre-materialised read models that serve data in exactly
the shape the UI needs — with edge-local latency — without coupling the read
path to the write schema.

---

## Context

In CQRS the **read side** is built from domain events or change notifications;
it has no joins, no business logic, only data shaped for display. Cloudflare
Workers KV is an ideal read-model store:

- Global replication with ≤60 ms eventual consistency
- ~1 ms P99 read latency from edge PoPs
- Up to 25 MiB per value (supports embedded list views)
- TTL-based expiry for time-bounded projections

A **projector** Worker subscribes to a Cloudflare Queue fed by the command side
and writes denormalised view records into KV. The read Worker serves these
directly without hitting D1.

```
Command side (D1 + DO)
    │ domain events → Queue
    ▼
Projector Worker
    │ writes KV keys
    ▼
KV (read model)
    ▲
Read Worker ← HTTP client
```

---

## Defining a Read Model Schema

```typescript
// Flat, query-optimised shape — no joins needed at read time
export interface UserProfileView {
  userId: string;
  displayName: string;
  email: string;
  avatarUrl: string | null;
  postCount: number;
  followerCount: number;
  followingCount: number;
  lastActiveAt: string; // ISO-8601
  plan: "free" | "pro" | "enterprise";
  updatedAt: string;
}

export interface PostFeedItem {
  postId: string;
  authorId: string;
  authorName: string;
  authorAvatarUrl: string | null;
  title: string;
  excerpt: string;
  publishedAt: string;
  likeCount: number;
  commentCount: number;
  tags: string[];
}

export interface UserFeedView {
  userId: string;
  items: PostFeedItem[];
  cursor: string | null; // opaque pagination token
  generatedAt: string;
}
```

---

## Projector Worker — Building Views from Events

```typescript
import type { MessageBatch, Message } from "@cloudflare/workers-types";

interface DomainEvent {
  type: string;
  aggregateId: string;
  payload: Record<string, unknown>;
  occurredAt: string;
}

interface Env {
  READ_MODEL_KV: KVNamespace;
  EVENT_QUEUE: Queue;
}

export default {
  async queue(batch: MessageBatch<DomainEvent>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await applyEvent(message.body, env);
        message.ack();
      } catch (err) {
        console.error("Projection failed", message.body.type, err);
        message.retry({ delaySeconds: 5 });
      }
    }
  },
};

async function applyEvent(event: DomainEvent, env: Env): Promise<void> {
  switch (event.type) {
    case "UserRegistered":
      await projectUserRegistered(event, env);
      break;
    case "UserDisplayNameChanged":
      await patchUserProfile(event.aggregateId, { displayName: event.payload.newName as string }, env);
      break;
    case "PostPublished":
      await projectPostPublished(event, env);
      break;
    case "PostLiked":
      await incrementField(
        `user:profile:${event.payload.authorId}`,
        "likeCount",
        env
      );
      break;
    default:
      // Ignore unknown events — projections only care about relevant events
      break;
  }
}

async function projectUserRegistered(
  event: DomainEvent,
  env: Env
): Promise<void> {
  const view: UserProfileView = {
    userId: event.aggregateId,
    displayName: event.payload.displayName as string,
    email: event.payload.email as string,
    avatarUrl: null,
    postCount: 0,
    followerCount: 0,
    followingCount: 0,
    lastActiveAt: event.occurredAt,
    plan: "free",
    updatedAt: event.occurredAt,
  };
  await env.READ_MODEL_KV.put(
    `user:profile:${event.aggregateId}`,
    JSON.stringify(view)
  );
}

async function patchUserProfile(
  userId: string,
  patch: Partial<UserProfileView>,
  env: Env
): Promise<void> {
  const existing = await env.READ_MODEL_KV.get<UserProfileView>(
    `user:profile:${userId}`,
    "json"
  );
  if (!existing) return; // event ordering issue — may arrive before UserRegistered
  const updated = { ...existing, ...patch, updatedAt: new Date().toISOString() };
  await env.READ_MODEL_KV.put(`user:profile:${userId}`, JSON.stringify(updated));
}

async function incrementField(
  key: string,
  field: string,
  env: Env
): Promise<void> {
  const view = await env.READ_MODEL_KV.get<Record<string, unknown>>(key, "json");
  if (!view) return;
  const current = (view[field] as number) ?? 0;
  view[field] = current + 1;
  view["updatedAt"] = new Date().toISOString();
  await env.READ_MODEL_KV.put(key, JSON.stringify(view));
}

async function projectPostPublished(
  event: DomainEvent,
  env: Env
): Promise<void> {
  // 1. Write individual post view
  const postKey = `post:${event.aggregateId}`;
  await env.READ_MODEL_KV.put(postKey, JSON.stringify(event.payload));

  // 2. Prepend to author's feed view (last 50 items)
  const authorId = event.payload.authorId as string;
  const feedKey = `user:feed:${authorId}`;
  const feed = (await env.READ_MODEL_KV.get<UserFeedView>(feedKey, "json")) ?? {
    userId: authorId,
    items: [],
    cursor: null,
    generatedAt: new Date().toISOString(),
  };
  const newItem: PostFeedItem = {
    postId: event.aggregateId,
    authorId,
    authorName: event.payload.authorName as string,
    authorAvatarUrl: event.payload.authorAvatarUrl as string | null,
    title: event.payload.title as string,
    excerpt: (event.payload.content as string).slice(0, 200),
    publishedAt: event.occurredAt,
    likeCount: 0,
    commentCount: 0,
    tags: event.payload.tags as string[],
  };
  feed.items = [newItem, ...feed.items].slice(0, 50);
  feed.generatedAt = new Date().toISOString();
  await env.READ_MODEL_KV.put(feedKey, JSON.stringify(feed));
}
```

---

## Read Worker — Serving Projections

```typescript
interface ReadEnv {
  READ_MODEL_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: ReadEnv): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/users/") && url.pathname.endsWith("/profile")) {
      const userId = url.pathname.split("/")[2];
      return serveView(`user:profile:${userId}`, env);
    }

    if (url.pathname.startsWith("/users/") && url.pathname.endsWith("/feed")) {
      const userId = url.pathname.split("/")[2];
      return serveView(`user:feed:${userId}`, env);
    }

    return new Response("Not Found", { status: 404 });
  },
};

async function serveView(key: string, env: ReadEnv): Promise<Response> {
  const { value, metadata } = await env.READ_MODEL_KV.getWithMetadata(key, "text");
  if (!value) return new Response("Not Found", { status: 404 });
  return new Response(value, {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, s-maxage=5, stale-while-revalidate=60",
      "X-View-Key": key,
    },
  });
}
```

---

## Projection Rebuild — Full Replay

When the read model schema changes, replay all events from D1 to rebuild KV:

```typescript
export async function rebuildProjection(env: Env): Promise<void> {
  const PAGE_SIZE = 500;
  let cursor = 0;

  while (true) {
    const { results } = await env.DB.prepare(
      "SELECT * FROM domain_events WHERE id > ? ORDER BY id ASC LIMIT ?"
    )
      .bind(cursor, PAGE_SIZE)
      .all<DomainEvent & { id: number }>();

    if (results.length === 0) break;

    for (const event of results) {
      await applyEvent(event, env);
    }

    cursor = results[results.length - 1].id;
    if (results.length < PAGE_SIZE) break;
  }
}
```

---

## Anti-patterns

- **Querying KV inside the projector with a read-modify-write loop without
  idempotency**: Duplicate queue messages replay events twice, double-counting
  counters. Use event ID deduplication or idempotent set operations.
- **Storing huge lists in a single KV value**: KV values max out at 25 MiB; a
  user with 10 000 posts overflows. Store paginated feeds as separate keys.
- **Coupling the read model to write-side table columns**: If D1 schema changes
  break projector deserialization, all reads fail. Define explicit event DTOs.
- **Treating KV as the source of truth**: KV is derivative; if lost, rebuild
  from the event log. Never write to KV from user actions directly.

---

## Gotchas

- KV has ~60 s eventual consistency globally; a client may read a stale view
  immediately after a write operation commits. Pair with `read-your-writes-consistency-workers-kv-d1.md`.
- KV `list()` is O(keys) not O(1) — avoid using it in hot read paths.
- Queue `retry()` replays the entire message; projectors must handle partial
  idempotency (e.g., `postCount` already incremented from a prior attempt).
- Projector fan-out (one event updating multiple KV keys) is not atomic — a
  crash mid-fan-out leaves the read model temporarily inconsistent until retry.

---

## Verification

```bash
# Check projection lag by comparing event timestamp vs KV updatedAt
wrangler kv:key get --namespace-id=<NS_ID> "user:profile:<userId>"

# Trigger manual rebuild via scheduled Worker or REST call
curl -X POST https://api.example.com/admin/projections/rebuild \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Monitor queue consumer lag
wrangler queues consumer get <queue-name>
```

---

## Related

- `cqrs-cloudflare-workers-d1.md`
- `event-sourcing-projections-snapshots.md`
- `kv-replication-lag-compensating-patterns.md`
- `materialized-view-maintenance.md`
- `read-your-writes-consistency-workers-kv-d1.md`

---

## Sources

- Cloudflare Workers KV documentation
- Cloudflare Queues documentation
- Greg Young — CQRS and Event Sourcing (2010)
- Martin Fowler — CQRS Pattern (martinfowler.com)
