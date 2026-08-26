# Event-Carried State Transfer: Workers and KV Read Models

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A feed Worker needs the display name, avatar hash, and karma score of every post author to render
a timeline. Querying D1 for each author on every request creates N+1 latency and contention on
the users table. A naïve solution adds a read replica, but in a globally distributed edge
environment that still means cross-continent round trips for collocated readers.

## Context

Cloudflare Workers run at the edge closest to the user. D1 is globally replicated but write
affinity is tied to a primary region. KV is eventually consistent but globally low-latency for
reads. Event-Carried State Transfer (ECST) ships the full denormalised snapshot of an entity
inside each domain event; consumers materialise that snapshot into KV, eliminating upstream
queries at read time.

## ECST vs. Event Notification

A plain event notification carries only an identifier: `{ userId: "u_abc" }`. The consumer must
call back to the source to fetch state, reintroducing coupling and latency. ECST embeds the full
relevant projection: `{ userId: "u_abc", displayName: "void", avatarHash: "sha:…", karma: 142 }`.
Consumers own their read models and never query the producing service.

```typescript
// Producer: UserService emits ECST event after any profile change.
interface UserSnapshotEvent {
  eventType: 'UserProfileUpdated';
  userId: string;
  displayName: string;      // full state — not a delta
  avatarHash: string;
  karma: number;
  updatedAt: number;        // epoch seconds for staleness checks
}

async function emitUserSnapshot(env: Env, userId: string): Promise<void> {
  const user = await env.DB.prepare(
    `SELECT display_name, avatar_hash, karma FROM users WHERE id = ?`
  )
    .bind(userId)
    .first<{ display_name: string; avatar_hash: string; karma: number }>();

  if (!user) return;

  const event: UserSnapshotEvent = {
    eventType: 'UserProfileUpdated',
    userId,
    displayName: user.display_name,
    avatarHash: user.avatar_hash,
    karma: user.karma,
    updatedAt: Math.floor(Date.now() / 1000),
  };

  await env.EVENTS.send(event);
}
```

## KV Read-Model Consumer

The Queue consumer writes the full snapshot to KV under a deterministic key. The TTL is set
generously (24 h) because ECST events keep the value fresh; the TTL is a safety net for
abandoned accounts, not the primary expiry mechanism.

```typescript
interface Env {
  EVENTS: Queue;
  USER_PROFILES: KVNamespace;
  DB: D1Database;
}

export default {
  async queue(
    batch: MessageBatch<UserSnapshotEvent>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const ev = msg.body;

      if (ev.eventType !== 'UserProfileUpdated') {
        msg.ack();
        continue;
      }

      const kvKey = `profile:${ev.userId}`;

      // Check for stale delivery (out-of-order re-delivery from retries).
      const existing = await env.USER_PROFILES.get<UserSnapshotEvent>(
        kvKey,
        'json'
      );
      if (existing && existing.updatedAt >= ev.updatedAt) {
        msg.ack(); // discard older snapshot
        continue;
      }

      await env.USER_PROFILES.put(kvKey, JSON.stringify(ev), {
        expirationTtl: 86_400,
      });

      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;
```

## Feed Worker Read Path

The feed Worker reads author snapshots from KV, falling back to D1 only on a cache miss. A miss
is rare after the first event delivery; the fallback also primes the cache for subsequent reads.

```typescript
interface UserProfile {
  displayName: string;
  avatarHash: string;
  karma: number;
}

async function getAuthorProfiles(
  env: Env,
  userIds: string[]
): Promise<Map<string, UserProfile>> {
  const map = new Map<string, UserProfile>();

  await Promise.all(
    userIds.map(async (id) => {
      const cached = await env.USER_PROFILES.get<UserProfile>(
        `profile:${id}`,
        'json'
      );

      if (cached) {
        map.set(id, cached);
        return;
      }

      // Cold fallback — also re-emits the event to warm the cache.
      const row = await env.DB.prepare(
        `SELECT display_name, avatar_hash, karma FROM users WHERE id = ?`
      )
        .bind(id)
        .first<{ display_name: string; avatar_hash: string; karma: number }>();

      if (row) {
        const profile: UserProfile = {
          displayName: row.display_name,
          avatarHash: row.avatar_hash,
          karma: row.karma,
        };
        await env.USER_PROFILES.put(`profile:${id}`, JSON.stringify(profile), {
          expirationTtl: 86_400,
        });
        map.set(id, profile);
      }
    })
  );

  return map;
}
```

## Staleness and Consistency Guarantees

KV offers eventual consistency with a replication lag typically under 60 seconds globally. For
example project's anonymous social context, displaying a slightly stale karma score or avatar on a feed
card is acceptable. Write-critical paths (profile edit confirmation, moderation actions) must
query D1 directly and must not rely on ECST projections.

```typescript
// Annotate the response so clients know data is eventually consistent.
function buildFeedResponse(
  posts: Post[],
  profiles: Map<string, UserProfile>
): Response {
  const body = posts.map((p) => ({
    id: p.id,
    body: p.body,
    author: profiles.get(p.authorId) ?? { displayName: '[unknown]', avatarHash: '', karma: 0 },
  }));

  return Response.json(
    { data: body, meta: { consistency: 'eventual' } },
    {
      headers: {
        'Cache-Control': 'public, max-age=10, stale-while-revalidate=60',
      },
    }
  );
}
```

## Anti-patterns

- Carrying only a diff/delta in the event — consumers must reconstruct state by replaying all
  deltas; KV is not designed for this.
- Using ECST for security-sensitive fields (raw tokens, PII beyond display names) — the snapshot
  propagates to multiple consumers with different trust levels.
- Trusting ECST read models for access control decisions — always re-validate permissions against
  the authoritative D1 source.
- Emitting huge payloads (>25 KB) — Queues message limits apply; use a Claim-Check pattern for
  large blobs and carry only the blob reference in the event.

## Gotchas

- KV TTL granularity is 1 second; values cannot have a zero TTL (use a high value and rely on
  event updates for liveness).
- `updatedAt` staleness guards only work if the producer sets a monotonically increasing
  timestamp; use D1's `unixepoch()` rather than `Date.now()` on the Worker side to avoid clock
  skew across edge PoPs.
- KV `list()` is eventually consistent; do not use it to enumerate profiles for batch operations
  — maintain an index in D1 instead.
- example project users are anonymous; `userId` should be an opaque token, not a resolvable identity,
  to prevent cross-consumer correlation.

## Verification

1. Update a user's karma in D1. Assert a `UserProfileUpdated` event appears in the Queue.
2. Process the Queue batch. Assert `profile:<userId>` in KV contains the new karma value.
3. Call the feed endpoint for a post by that user. Assert the response contains the updated karma
   without touching D1 (instrument with a D1 query counter in test mode).
4. Replay the same event with an earlier `updatedAt`. Assert KV value is unchanged.

## Related

- [Event-Carried State Transfer](event-carried-state-transfer.md)
- [Read Model Projection — Workers, KV, CQRS](read-model-projection-workers-kv-cqrs.md)
- [KV Replication Lag Compensating Patterns](kv-replication-lag-compensating-patterns.md)
- [CQRS — Cloudflare Workers D1](cqrs-cloudflare-workers-d1.md)
- [Claim-Check Pattern — Large Messages](claim-check-pattern-large-messages.md)

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/queues/
- https://martinfowler.com/articles/201701-event-driven.html
- https://developers.cloudflare.com/d1/
