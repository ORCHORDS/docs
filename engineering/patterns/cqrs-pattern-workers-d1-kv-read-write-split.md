# CQRS Pattern: Workers D1/KV Read-Write Split

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Write-heavy social operations (post creation, reactions, follows) contend with read-heavy feed queries on the same D1 database, causing tail-latency spikes and lock contention. Analytics queries that scan millions of rows slow down transactional writes that need to complete in under 50 ms. A single database handle cannot serve both workloads without sacrificing one.

## Context

Cloudflare Workers run at the edge with sub-millisecond startup. D1 is a SQLite-based distributed database with strong consistency on writes but eventual consistency on read replicas. KV offers globally replicated, eventually consistent reads with very low latency. Combining D1 for writes with KV for read projections matches the CQRS (Command Query Responsibility Segregation) model naturally — commands mutate D1, queries read from KV projections rebuilt asynchronously.

## Command Side — Writes to D1

Every mutating operation is a "command" that goes to D1. The command handler validates, writes, then enqueues a projection event. Using a Cloudflare Queue decouples the write path from view rebuilding so the HTTP response returns immediately.

```typescript
// src/commands/post-create.ts
import type { Env } from '../env';

export interface CreatePostCommand {
  authorId: string;
  body: string;
  parentId?: string;
}

export interface PostCreatedEvent {
  type: 'POST_CREATED';
  postId: string;
  authorId: string;
  body: string;
  parentId?: string;
  createdAt: string;
}

export async function handleCreatePost(
  cmd: CreatePostCommand,
  env: Env
): Promise<{ postId: string }> {
  const postId = crypto.randomUUID();
  const createdAt = new Date().toISOString();

  // Write canonical record to D1 (the system of record)
  await env.DB.prepare(
    `INSERT INTO posts (id, author_id, body, parent_id, created_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(cmd.authorId, cmd.body, cmd.parentId ?? null, createdAt, postId).run();

  // Publish projection event — do not await KV update inline
  const event: PostCreatedEvent = {
    type: 'POST_CREATED',
    postId,
    authorId: cmd.authorId,
    body: cmd.body,
    parentId: cmd.parentId,
    createdAt,
  };
  await env.PROJECTION_QUEUE.send(event);

  return { postId };
}
```

## Query Side — Reads from KV Projections

The query side never touches D1 in the hot path. KV holds pre-built JSON projections keyed by access pattern. Feed reads resolve in single-digit milliseconds from the nearest PoP.

```typescript
// src/queries/feed.ts
import type { Env } from '../env';

export interface FeedPost {
  postId: string;
  authorHandle: string;
  body: string;
  reactionCount: number;
  createdAt: string;
}

export interface FeedView {
  posts: FeedPost[];
  nextCursor?: string;
}

// KV key schema: feed:{userId}:{cursor}
export async function queryUserFeed(
  userId: string,
  cursor: string | null,
  env: Env
): Promise<FeedView> {
  const key = cursor
    ? `feed:${userId}:${cursor}`
    : `feed:${userId}:latest`;

  const raw = await env.FEED_CACHE.get(key, 'json') as FeedView | null;
  if (raw) return raw;

  // Cold path: fall back to D1 and prime the projection
  return queryFeedFromD1(userId, cursor, env);
}

async function queryFeedFromD1(
  userId: string,
  cursor: string | null,
  env: Env
): Promise<FeedView> {
  const limit = 20;
  const result = await env.DB.prepare(
    `SELECT p.id, u.handle, p.body, COUNT(r.id) AS reaction_count, p.created_at
     FROM posts p
     JOIN users u ON u.id = p.author_id
     LEFT JOIN reactions r ON r.post_id = p.id
     WHERE p.author_id IN (
       SELECT followee_id FROM follows WHERE follower_id = ?
     )
     AND (? IS NULL OR p.created_at < ?)
     GROUP BY p.id
     ORDER BY p.created_at DESC
     LIMIT ?`
  ).bind(userId, cursor, cursor, limit).all<{
    id: string; handle: string; body: string;
    reaction_count: number; created_at: string;
  }>();

  const posts: FeedPost[] = result.results.map(r => ({
    postId: r.id,
    authorHandle: r.handle,
    body: r.body,
    reactionCount: r.reaction_count,
    createdAt: r.created_at,
  }));

  const view: FeedView = {
    posts,
    nextCursor: posts.at(-1)?.createdAt,
  };

  // Prime KV — TTL 60 s, stale-while-revalidate via queue
  await env.FEED_CACHE.put(
    `feed:${userId}:${cursor ?? 'latest'}`,
    JSON.stringify(view),
    { expirationTtl: 60 }
  );
  return view;
}
```

## Projection Consumer — Rebuilding KV from Queue Events

A Queue consumer receives projection events and updates the affected KV keys. This is the only code that knows both sides of the split.

```typescript
// src/consumers/projection-consumer.ts
import type { Env } from '../env';
import type { PostCreatedEvent } from '../commands/post-create';

type ProjectionEvent = PostCreatedEvent; // union as more event types added

export async function handleProjectionBatch(
  batch: MessageBatch<ProjectionEvent>,
  env: Env
): Promise<void> {
  const invalidatedUsers = new Set<string>();

  for (const msg of batch.messages) {
    const event = msg.body;
    switch (event.type) {
      case 'POST_CREATED':
        invalidatedUsers.add(event.authorId);
        // Invalidate followers' feeds too
        await invalidateFollowerFeeds(event.authorId, invalidatedUsers, env);
        break;
    }
    msg.ack();
  }

  // Delete stale KV projections — next read will cold-path rebuild
  await Promise.all(
    [...invalidatedUsers].map(uid =>
      env.FEED_CACHE.delete(`feed:${uid}:latest`)
    )
  );
}

async function invalidateFollowerFeeds(
  authorId: string,
  set: Set<string>,
  env: Env
): Promise<void> {
  const followers = await env.DB.prepare(
    `SELECT follower_id FROM follows WHERE followee_id = ? LIMIT 1000`
  ).bind(authorId).all<{ follower_id: string }>();
  followers.results.forEach(r => set.add(r.follower_id));
}
```

## Routing — Separate Command and Query Endpoints

```typescript
// src/router.ts
import { handleCreatePost } from './commands/post-create';
import { queryUserFeed } from './queries/feed';
import type { Env } from './env';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    // Commands — always hit D1, authoritative
    if (req.method === 'POST' && url.pathname === '/posts') {
      const body = await req.json<{ body: string; parentId?: string }>();
      const userId = req.headers.get('x-user-id')!;
      const result = await handleCreatePost(
        { authorId: userId, body: body.body, parentId: body.parentId },
        env
      );
      return Response.json(result, { status: 201 });
    }

    // Queries — read from KV, never block writes
    if (req.method === 'GET' && url.pathname === '/feed') {
      const userId = req.headers.get('x-user-id')!;
      const cursor = url.searchParams.get('cursor');
      const feed = await queryUserFeed(userId, cursor, env);
      return Response.json(feed);
    }

    return new Response('Not Found', { status: 404 });
  },

  async queue(batch: MessageBatch, env: Env): Promise<void> {
    const { handleProjectionBatch } = await import('./consumers/projection-consumer');
    await handleProjectionBatch(batch as MessageBatch<any>, env);
  },
};
```

## Anti-patterns

- Reading from D1 on every GET request — defeats the purpose; KV is the query store
- Updating KV synchronously inside the command handler — adds latency and coupling
- Sharing a single D1 query model for both commands and queries — leads to N+1 fetches for projections
- Rebuilding entire user feed projections on every event — batch invalidation and lazy rebuild instead
- Skipping event ordering — Queue FIFO mode required when projection order matters

## Gotchas

- KV replication lag is up to 60 s globally; reads may be stale for that window; use `metadata` TTL tracking to detect
- D1 read replicas are eventually consistent; the query fall-back path can also return slightly stale data
- Queue consumer retries mean projection events can replay; make invalidation idempotent (deleting a key twice is safe)
- `wrangler.toml` must declare both `[[d1_databases]]` and `[[queues.consumers]]` bindings
- Cold projection rebuilds fire D1 scans; add a Durable Object rate-limiter to prevent stampedes after long queue lag

## Verification

```bash
# 1. POST a new post; confirm D1 write
curl -X POST https://example.com/posts \
  -H 'x-user-id: user-123' \
  -d '{"body":"hello"}' | jq .postId

# 2. Check KV feed key is invalidated after queue processes
wrangler kv key get --binding FEED_CACHE "feed:user-123:latest"
# Should return null until rebuilt

# 3. GET feed — first call triggers cold-path D1 scan, primes KV
curl https://example.com/feed -H 'x-user-id: user-123' | jq .posts[0]

# 4. Subsequent GET should be served from KV (check CF-Cache-Status header or timing)
```

## Related

- `documentation/categories/patterns/cache-aside-kv-d1-fallback.md`
- `documentation/categories/patterns/outbox-pattern-d1-reliable-publishing.md`
- `documentation/categories/patterns/event-driven-architecture.md`
- `documentation/categories/patterns/fan-out-queues-workers.md`
- `documentation/categories/patterns/materialized-view-d1-workers.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/queues/
- https://martinfowler.com/bliki/CQRS.html
- https://developers.cloudflare.com/queues/configuration/javascript-apis/#messagebatch
