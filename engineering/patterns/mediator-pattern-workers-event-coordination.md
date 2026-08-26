# Mediator Pattern: Workers Event Coordination

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project has a growing list of subsystems — ranking, notifications, moderation triggers, analytics, search indexing — that all need to react when a post is created, voted on, or reported. Directly calling each subsystem from the post-write handler creates tight coupling: every new subscriber means editing the handler, and a failure in one system (e.g., notification push) can cascade to block the write.

## Context

A Cloudflare Worker acting as an event mediator receives domain events from producers and dispatches them to subscriber Workers via Service Bindings or Queues. The mediator is the sole point of coupling; producers and consumers never reference each other. This pattern complements the Command pattern (action log) and fits naturally between the write path and the fan-out consumers.

## Pattern Overview — EventBus Interface

The mediator exposes a typed `EventBus` that producers call. Internally it resolves subscriber Workers from the Env bindings and dispatches events concurrently using `Promise.allSettled` so one failing subscriber does not block others.

```typescript
// mediator/types.ts
export type DomainEvent =
  | { event: 'post.created';  postId: string;   boardSlug: string; authorHash: string; ts: number }
  | { event: 'post.upvoted';  postId: string;   voterHash: string; ts: number }
  | { event: 'post.reported'; contentId: string; reason: string;   ts: number }
  | { event: 'user.joined';   boardSlug: string; authorHash: string; ts: number };

export interface EventSubscriber {
  receiveEvent(event: DomainEvent, env: MediatorEnv): Promise<void>;
}

export interface MediatorEnv {
  RANKING_WORKER:      Fetcher;
  NOTIFICATION_WORKER: Fetcher;
  MODERATION_WORKER:   Fetcher;
  ANALYTICS_QUEUE:     Queue<DomainEvent>;
  EVENT_LOG:           D1Database;
}
```

## Implementation — The Mediator

The `EventMediator` class holds a registry mapping event types to named subscribers. The registry is built from `MediatorEnv` bindings so that no subscriber is hard-coded in the mediator logic itself — only in `wrangler.toml` service-binding declarations.

```typescript
// mediator/event-mediator.ts
import { DomainEvent, EventSubscriber, MediatorEnv } from './types';
import { RankingSubscriber }      from './subscribers/ranking';
import { NotificationSubscriber } from './subscribers/notification';
import { ModerationSubscriber }   from './subscribers/moderation';

type SubscriberFactory = (env: MediatorEnv) => EventSubscriber;

const REGISTRY: Partial<Record<DomainEvent['event'], SubscriberFactory[]>> = {
  'post.created':  [
    env => new RankingSubscriber(env.RANKING_WORKER),
    env => new NotificationSubscriber(env.NOTIFICATION_WORKER),
    env => new ModerationSubscriber(env.MODERATION_WORKER),
  ],
  'post.upvoted':  [
    env => new RankingSubscriber(env.RANKING_WORKER),
  ],
  'post.reported': [
    env => new ModerationSubscriber(env.MODERATION_WORKER),
  ],
  'user.joined':   [
    env => new NotificationSubscriber(env.NOTIFICATION_WORKER),
  ],
};

export class EventMediator {
  constructor(private env: MediatorEnv) {}

  async dispatch(event: DomainEvent): Promise<{ failed: number }> {
    // Persist to event log before dispatching (at-least-once guarantee)
    await this.env.EVENT_LOG
      .prepare('INSERT INTO event_log (event_type, payload, occurred_at) VALUES (?, ?, ?)')
      .bind(event.event, JSON.stringify(event), event.ts)
      .run();

    // Enqueue for analytics (fire-and-forget via Queues)
    await this.env.ANALYTICS_QUEUE.send(event);

    const factories = REGISTRY[event.event] ?? [];
    const subscribers = factories.map(f => f(this.env));

    const results = await Promise.allSettled(
      subscribers.map(s => s.receiveEvent(event, this.env)),
    );

    const failed = results.filter(r => r.status === 'rejected').length;
    if (failed > 0) {
      console.error(`Mediator: ${failed}/${subscribers.length} subscribers failed for ${event.event}`);
    }
    return { failed };
  }
}
```

## Implementation — Subscriber Adapters

Each subscriber wraps a Service Binding call, translating the domain event into the contract the downstream Worker expects. Subscribers are thin adapters — business logic lives in the target Worker, not here.

```typescript
// mediator/subscribers/ranking.ts
import { EventSubscriber, DomainEvent, MediatorEnv } from '../types';

export class RankingSubscriber implements EventSubscriber {
  constructor(private fetcher: Fetcher) {}

  async receiveEvent(event: DomainEvent, _env: MediatorEnv): Promise<void> {
    const res = await this.fetcher.fetch('https://ranking/ingest', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(event),
    });
    if (!res.ok) throw new Error(`Ranking subscriber rejected event: ${res.status}`);
  }
}

// mediator/subscribers/notification.ts
import { EventSubscriber, DomainEvent, MediatorEnv } from '../types';

export class NotificationSubscriber implements EventSubscriber {
  constructor(private fetcher: Fetcher) {}

  async receiveEvent(event: DomainEvent, _env: MediatorEnv): Promise<void> {
    // Only dispatch notification-relevant events
    if (event.event !== 'post.created' && event.event !== 'user.joined') return;
    const res = await this.fetcher.fetch('https://notifications/push', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(event),
    });
    if (!res.ok) throw new Error(`Notification subscriber error: ${res.status}`);
  }
}

// mediator/subscribers/moderation.ts
import { EventSubscriber, DomainEvent, MediatorEnv } from '../types';

export class ModerationSubscriber implements EventSubscriber {
  constructor(private fetcher: Fetcher) {}

  async receiveEvent(event: DomainEvent, _env: MediatorEnv): Promise<void> {
    const res = await this.fetcher.fetch('https://moderation/enqueue', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(event),
    });
    if (!res.ok) throw new Error(`Moderation subscriber error: ${res.status}`);
  }
}
```

## Workers Integration — Mediator Entry Point

The mediator is deployed as a separate Worker. Producers call it via Service Binding (`env.EVENT_BUS.fetch(...)`) rather than over the public internet.

```typescript
// mediator-worker.ts — wrangler name: event-mediator
import { EventMediator }  from './mediator/event-mediator';
import { DomainEvent, MediatorEnv } from './mediator/types';

export default {
  async fetch(request: Request, env: MediatorEnv): Promise<Response> {
    if (request.method !== 'POST') return new Response('', { status: 405 });

    let event: DomainEvent;
    try {
      event = (await request.json()) as DomainEvent;
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    const mediator = new EventMediator(env);
    const { failed } = await mediator.dispatch(event);

    // Return 207 Multi-Status when some subscribers failed but the event was logged
    const status = failed > 0 ? 207 : 200;
    return Response.json({ dispatched: true, failed }, { status });
  },
};

// Example: producer Worker calling the mediator via Service Binding
/*
  await env.EVENT_BUS.fetch('https://event-mediator/dispatch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event: 'post.created',
      postId: newPostId,
      boardSlug: 'general',
      authorHash: 'h123',
      ts: Date.now(),
    }),
  });
*/
```

## Anti-patterns

- Putting subscriber business logic inside the mediator — the mediator is a router, not an actor; keep subscriber adapters thin
- Making subscribers call back into the mediator to dispatch further events — creates cycles; use the Queues fan-out path for chained events
- Using `Promise.all` instead of `Promise.allSettled` for dispatch — a single subscriber failure aborts all remaining dispatches
- Deploying the mediator and all subscribers in a single bundled Worker — defeats independent deployment and scaling of each subsystem
- Logging the full payload at DEBUG level in production — events may contain pseudonymous hashes that, combined, become identifiable

## Gotchas

- Service Binding calls count as subrequests; each Worker invocation is capped at 1000 subrequests and a 30s wall-clock time — batch or queue high-volume events
- `Promise.allSettled` settles after the slowest subscriber; set aggressive per-fetch timeouts using `AbortSignal.timeout(2000)` to avoid holding the response open
- The event log in D1 grows unboundedly; add a TTL-based cleanup cron (`DELETE FROM event_log WHERE occurred_at < unixepoch() - 604800`)
- When testing with `@cloudflare/vitest-pool-workers`, Service Binding calls to sibling Workers require `experimental_services` in `wrangler.toml`

## Verification

```bash
# Smoke-test via wrangler dev
curl -X POST http://localhost:8787/ \
  -H 'Content-Type: application/json' \
  -d '{"event":"post.created","postId":"p1","boardSlug":"general","authorHash":"h1","ts":1700000000000}'
# Expect: {"dispatched":true,"failed":0} or {"dispatched":true,"failed":N}

# Inspect event log
npx wrangler d1 execute example project-db --local \
  --command "SELECT event_type, occurred_at FROM event_log ORDER BY occurred_at DESC LIMIT 10"
```

## Related

- `observer-pattern-workers-durable-objects-event-bus.md` — DO-backed pub/sub for real-time subscribers
- `fan-out-queues-workers.md` — queue-based fan-out without synchronous Service Binding calls
- `command-pattern-workers-queues-action-log.md` — command log that feeds the mediator's event stream
- `correlation-id-propagation-workers.md` — tracing event chains across Workers
- `scatter-gather-parallel-workers.md` — parallel subrequest pattern used inside `dispatch`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
- https://refactoring.guru/design-patterns/mediator
