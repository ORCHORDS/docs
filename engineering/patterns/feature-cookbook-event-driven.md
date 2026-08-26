# feature-cookbook-event-driven

**Issue:** Event-driven architecture — pub/sub, queues, events
**Date:** 2026-08-09
**Status:** documented

## Symptom
You have a "user signed up" flow. The user signs up.
You need to: send a welcome email, create a default
workspace, log an analytics event, notify the admin.
You put all this in the signup function. The function
takes 5 seconds. The user is frustrated.

## Root cause
**Side effects in the request path are slow.** Use
events.

**Source:** AWS — Event-driven architecture.

## The "event" concept

An event is a fact: "something happened." Events are
immutable, named, and timestamped.

```json
{
  "type": "user.signed_up",
  "version": 1,
  "occurredAt": "2026-08-09T12:00:00Z",
  "data": {
    "userId": "u_123",
    "email": "alice@example.com"
  }
}
```

The event is a fact.

## The "pub/sub" pattern

For pub/sub, the publisher + subscribers:
```ts
// 1. Publisher
await env.QUEUE.send({
  type: 'user.signed_up',
  data: { userId: user.id, email: user.email },
});

// 2. Subscriber (email service)
async function handleUserSignedUp(event: Event, env: Env): Promise<void> {
  await sendEmail({
    to: event.data.email,
    subject: 'Welcome!',
    html: '<h1>Welcome to our app</h1>',
  }, env);
}
```

The publisher doesn't know the subscribers.

## The "queue-based" pattern

For queues, use CF Queues:
```ts
// Producer
await env.QUEUE.send({ type: 'process_user', userId: 'u_123' });

// Consumer
export default {
  async queue(batch: MessageBatch<Job>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processUser(message.body, env);
        message.ack();
      } catch (err) {
        message.retry();
      }
    }
  },
};
```

The queue handles delivery.

## The "event bus" pattern

For an event bus:
```ts
class EventBus {
  private handlers = new Map<string, Array<(event: any) => Promise<void>>>();

  on(type: string, handler: (event: any) => Promise<void>): void {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type)!.push(handler);
  }

  async emit(event: Event): Promise<void> {
    const handlers = this.handlers.get(event.type) ?? [];
    await Promise.all(handlers.map(h => h(event)));
  }
}

const bus = new EventBus();
bus.on('user.signed_up', sendWelcomeEmail);
bus.on('user.signed_up', createDefaultWorkspace);
bus.on('user.signed_up', logAnalytics);

await bus.emit({ type: 'user.signed_up', data: { ... } });
```

The bus dispatches to multiple handlers.

## The "event schema" pattern

For event schemas, use a registry:
```ts
const EventSchemas = {
  'user.signed_up': z.object({
    userId: z.string().uuid(),
    email: z.string().email(),
    signedUpAt: z.string().datetime(),
  }),
  'user.deleted': z.object({
    userId: z.string().uuid(),
    deletedAt: z.string().datetime(),
  }),
};

function validateEvent<T extends keyof typeof EventSchemas>(
  type: T,
  data: any
): z.infer<typeof EventSchemas[T]> {
  return EventSchemas[type].parse(data);
}
```

The schema is enforced.

## The "event versioning" pattern

For event versioning, add a version:
```ts
// v1
{ type: 'user.signed_up', version: 1, data: { userId, email } }

// v2 (added displayName)
{ type: 'user.signed_up', version: 2, data: { userId, email, displayName } }
```

The version is in the event.

## The "idempotent event handler" pattern

For retries, the handler is idempotent:
```ts
async function handleUserSignedUp(event: Event, env: Env): Promise<void> {
  // Idempotency: process only once
  const processed = await env.KV.get(`processed:${event.data.userId}`);
  if (processed) return;

  await sendWelcomeEmail(event.data, env);
  await env.KV.put(`processed:${event.data.userId}`, '1', { expirationTtl: 86400 * 30 });
}
```

The handler is idempotent.

## The "dead letter queue" pattern

For failed events, DLQ:
```ts
async function processWithDLQ(event: Event, env: Env): Promise<void> {
  const attempts = await getAttempts(event.id, env);

  try {
    await handleEvent(event, env);
    await env.KV.delete(`attempts:${event.id}`);
  } catch (err) {
    if (attempts >= 5) {
      await env.DLQ.send({ ...event, error: String(err) });
      return;
    }
    await env.KV.put(`attempts:${event.id}`, String(attempts + 1));
    throw err;
  }
}
```

Failed events go to DLQ.

## The "event sourcing" pattern

For event sourcing, the events are the source of truth:
```ts
// State is derived from events
async function getUserState(userId: string, env: Env): Promise<UserState> {
  const events = await env.DB!.prepare(
    `SELECT * FROM events WHERE aggregate_id = ? ORDER BY timestamp`
  ).bind(userId).all();

  return events.results.reduce(applyEvent, initialState);
}
```

The events are the data.

## The "event-driven anti-pattern" anti-patterns

### 1. Side effects in the request path
- **Issue:** The request is slow
- **Fix:** Use events

### 2. Tight coupling
- **Issue:** Service A calls Service B directly
- **Fix:** Use events

### 3. No idempotency
- **Issue:** Retries do the work twice
- **Fix:** Idempotency keys

### 4. No event schema
- **Issue:** Inconsistent events
- **Fix:** Use a schema registry

### 5. No DLQ
- **Issue:** Failed events are lost
- **Fix:** Use a DLQ

### 6. Synchronous events
- **Issue:** The request is still slow
- **Fix:** Use async queues

## The "event-driven vs request-response" choice

| Use case | Use |
|---|---|
| **Real-time response** | Request-response |
| **Async work** | Events |
| **Cross-service** | Events |
| **Simple CRUD** | Request-response |
| **Side effects** | Events |

For most apps, **a mix of both**.

## Verification
- **Test:** Events are dispatched
- **Test:** Idempotency works
- **Test:** DLQ captures failures
- **Live:** Event flow is monitored
- **Audit:** Quarterly event review

## Gotchas
- **The "side effects in the request path" anti-pattern.**
  Use events.
- **The "no idempotency" anti-pattern.** Make handlers
  idempotent.
- **The "no DLQ" anti-pattern.** Capture failed events.
- **The "no event schema" anti-pattern.** Validate
  events.

## Related
- `event-driven-architecture.md`
- `event-sourcing.md`
- `saga-pattern.md`
- `feature-cookbook-saga.md`
- `feature-cookbook-queues.md`
- `cloudflare/workers-workers-queues-patterns.md`
- `idempotency-keys.md`
- AWS event-driven: https://aws.amazon.com/event-driven-architecture/
