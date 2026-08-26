# Shared-Nothing Architecture: Workers and Durable Objects

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project's feed endpoint handles unpredictable viral spikes: a single popular post can cause
requests per second to leap by three orders of magnitude in under a minute. Shared in-process
state (global variables, module-level caches, connection pools) becomes a contention bottleneck
and a source of cross-request data leakage — a severe concern for an anonymous platform. The
system must scale to zero and to thousands of concurrent Workers without coordination overhead.

## Context

Cloudflare Workers are isolated V8 isolates. Each isolate shares no heap with any other isolate
— even within the same PoP. Module-level variables survive for the lifetime of the isolate but
are not shared across isolates, and the platform may spawn new isolates or evict old ones at any
time. Shared-Nothing Architecture (SNA) formalises this: each processing unit owns no mutable
state; all state is externalised to Durable Objects, D1, KV, or R2, each accessed through
well-defined APIs.

## Shared-Nothing Principle in Workers

A Worker is stateless by construction. The only persistent state surfaces are:

| Store | Consistency | Latency | Use for |
|-------|-------------|---------|---------|
| Durable Object | Strong (single-writer) | Low (co-located) | Per-entity counters, session state |
| D1 | Serialisable within primary | Medium | Relational queries, writes |
| KV | Eventual | Very low (edge) | Read-heavy, tolerates stale |
| R2 | Strong per object | Low | Large blobs, media |

No Worker should maintain mutable state in module scope beyond configuration constants and
pre-compiled patterns.

```typescript
// WRONG — module-level mutable cache shared across concurrent requests in the same isolate.
const profileCache = new Map<string, UserProfile>(); // DANGER: leaks between requests

// RIGHT — state lives in KV; each request is independent.
async function getProfile(env: Env, userId: string): Promise<UserProfile | null> {
  return env.USER_PROFILES.get<UserProfile>(`profile:${userId}`, 'json');
}
```

## Durable Objects as the Single-Writer Node

When coordination between Workers is required (e.g., a real-time view counter), a Durable Object
provides a single-writer, strongly consistent store. All Workers that need to read or mutate the
counter send requests to the same DO instance, identified by a deterministic key. The DO itself
shares nothing with other DOs — each instance is isolated.

```typescript
export class ViewCounter extends DurableObject {
  async increment(postId: string): Promise<number> {
    const key = `views:${postId}`;
    const current = (await this.ctx.storage.get<number>(key)) ?? 0;
    const next = current + 1;
    await this.ctx.storage.put(key, next);
    return next;
  }

  async get(postId: string): Promise<number> {
    return (await this.ctx.storage.get<number>(`views:${postId}`)) ?? 0;
  }
}

// Worker — no shared state; all coordination goes through the DO.
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const postId = new URL(request.url).searchParams.get('postId') ?? '';
    const doId = env.VIEW_COUNTER.idFromName(postId);
    const counter = env.VIEW_COUNTER.get(doId);

    if (request.method === 'POST') {
      const views = await counter.increment(postId);
      return Response.json({ views });
    }

    const views = await counter.get(postId);
    return Response.json({ views });
  },
} satisfies ExportedHandler<Env>;
```

## Stateless Request Pipeline

Design each request handler as a pure function of its inputs and the externalised stores. This
makes the handler trivially testable, hot-reloadable, and safe for the platform to run on any
available isolate without sticky routing.

```typescript
interface FeedRequest {
  cursor?: string;
  limit: number;
}

interface FeedItem {
  id: string;
  body: string;
  views: number;
  authorKarma: number;
}

// Pure function: takes env (external state handles) + request data, returns response.
async function buildFeed(env: Env, req: FeedRequest): Promise<FeedItem[]> {
  const posts = await env.DB.prepare(
    `SELECT id, body, author_id FROM posts
     WHERE id < COALESCE(?, 'zzzzzzzz')
     ORDER BY id DESC LIMIT ?`
  )
    .bind(req.cursor ?? null, req.limit)
    .all<{ id: string; body: string; author_id: string }>();

  return Promise.all(
    posts.results.map(async (post) => {
      const [profile, views] = await Promise.all([
        env.USER_PROFILES.get<{ karma: number }>(`profile:${post.author_id}`, 'json'),
        env.VIEW_COUNTER.get(env.VIEW_COUNTER.idFromName(post.id)).get(post.id),
      ]);

      return {
        id: post.id,
        body: post.body,
        views,
        authorKarma: profile?.karma ?? 0,
      };
    })
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const items = await buildFeed(env, {
      cursor: url.searchParams.get('cursor') ?? undefined,
      limit: Math.min(Number(url.searchParams.get('limit') ?? 20), 100),
    });
    return Response.json({ data: items });
  },
} satisfies ExportedHandler<Env>;
```

## Isolation for Anonymous Platforms

Shared-nothing is a security property for example project as much as a scalability property. Module-
level caches can bleed data between requests; in an anonymous context, leaking a previous user's
content into the current response would be a serious privacy breach. SNA eliminates this class
of bug structurally.

```typescript
// Demonstrate that no cross-request leakage is possible when state is externalised.
// Each request fetches its own view of the world from the stores;
// there is no shared buffer, queue, or map in module scope that could intermix values.

// Safe: read-only constants compiled once per isolate.
const CONTENT_POLICY_VERSION = 'v3';
const MAX_POST_BYTES = 2_048;

// Safe: immutable compiled regex.
const SLUR_PATTERN = /\b(badword1|badword2)\b/i;
```

## Anti-patterns

- Caching mutable entity state in `globalThis` or module scope — the cache is invisible to other
  isolates and may serve stale or privacy-violating data within the same isolate across requests.
- Using a single Durable Object as a global fan-out hub — a single DO is a single-writer
  bottleneck; shard by entity ID.
- Storing WebSocket connection handles in a module-level map outside a Durable Object — handles
  are not shared across isolates; only the DO that accepted the connection holds it.
- Assuming a Worker's isolate is long-lived — the platform evicts isolates under memory pressure;
  module-level initialisation must be idempotent and cheap.

## Gotchas

- Durable Object storage is durable but the in-memory state of the DO class is not — a DO
  eviction resets all JavaScript properties; always read from `this.ctx.storage` on each method
  entry or cache carefully with an explicit reload pattern.
- `idFromName()` is deterministic but case-sensitive; normalise all entity IDs to lowercase
  before generating a DO ID to avoid phantom duplicates.
- Concurrent Workers can issue simultaneous requests to the same DO; the DO's single-threaded
  event loop serialises them, but handlers must not await external calls while holding implicit
  locks — use optimistic patterns instead.
- D1 read replicas may lag the primary; for example project vote counts and karma, read from D1 primary
  or use a DO for the hot counter and sync to D1 asynchronously.

## Verification

1. Deploy two concurrent Worker instances (simulate with Miniflare's multi-worker mode). Write a
   value to module-level state in instance A. Assert instance B does not observe it.
2. Issue #<number>,000 concurrent `POST /view` requests for the same post. Assert the DO counter reaches
   exactly 1,000 (no lost increments due to races).
3. Restart the DO (evict via Miniflare API). Assert counter value persists from storage.
4. Search the codebase for module-level `let`/`const` declarations that mutate after module
   load; flag any that hold non-configuration state.

## Related

- [Actor Model — Durable Objects and Workers](actor-model-durable-objects-workers.md)
- [Multi-Region Active-Active — Durable Objects](multi-region-active-active-durable-objects.md)
- [Data Isolation Strategies](data-isolation-strategies.md)
- [Session Stickiness — Durable Objects Workers Routing](session-stickiness-durable-objects-workers-routing.md)
- [Competing Consumers — Durable Objects](competing-consumers-durable-objects.md)

## Sources

- https://developers.cloudflare.com/workers/reference/how-workers-works/
- https://developers.cloudflare.com/durable-objects/
- https://developers.cloudflare.com/durable-objects/api/state/
- https://en.wikipedia.org/wiki/Shared-nothing_architecture
