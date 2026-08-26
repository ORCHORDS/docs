# event-sourcing

**Issue:** When to use event sourcing vs CRUD
**Date:** 2026-08-09
**Status:** documented (architectural decision)

## Symptom
You build a platform. Users create posts, edit them, delete them.
A year later, the legal team asks "show me every state this post
was ever in, with timestamps and actor." You can't — you only
have the current state. The audit log is separate and doesn't
have the post content.

## Root cause
**CRUD (Create, Read, Update, Delete)** stores current state.
The history is implicit (you can diff backups, but that's not
queryable). For audit + compliance + debugging, you need
explicit history.

**Source:** Martin Fowler — Event Sourcing:
https://martinfowler.com/eaaDev/EventSourcing.html

> "The fundamental idea of Event Sourcing is that of ensuring
> every change to the state of an application is captured in
> an event object, and that these event objects are themselves
> stored in the sequence they were applied for the same entity."

## When to use event sourcing

✅ Use event sourcing when:
- **The history is a first-class concern** (audit, compliance,
  debugging)
- **You need to time-travel** (what did this look like 6 months
  ago?)
- **Multiple consumers need different views** (the same events
  feed an audit log, a search index, and a notification system)
- **You need to replay** (after a bug, replay events to rebuild
  state correctly)

❌ Don't use event sourcing when:
- **The current state is all that matters** (CRUD is simpler)
- **The data is mostly read-only** (a blog post, a knowledge
  base article)
- **You can't store events indefinitely** (event stores grow
  unbounded; you need a strategy for "cold" events)
- **The team is unfamiliar with the pattern** (CQRS + event
  sourcing is hard; CRUD + a separate audit log is much easier)

## The pattern

```ts
// The event store
interface Event {
  id: string;
  aggregateId: string;  // e.g. "post_123"
  type: string;         // e.g. "post.created"
  data: unknown;        // event payload
  actor: { id: string; type: 'user' | 'system' };
  timestamp: number;    // UNIX seconds
  prevEventHash: string;  // for Merkle chain
}

// Commands (intention) vs events (fact)
type Command =
  | { type: 'createPost'; title: string; content: string }
  | { type: 'updatePost'; postId: string; title: string; content: string }
  | { type: 'deletePost'; postId: string };

// The command handler produces events
function handleCommand(cmd: Command, env: Env, ctx: McContext): Event[] {
  switch (cmd.type) {
    case 'createPost':
      return [{
        id: crypto.randomUUID(),
        aggregateId: `post_${crypto.randomUUID()}`,
        type: 'post.created',
        data: { title: cmd.title, content: cmd.content, authorId: ctx.user.id },
        actor: { id: ctx.user.id, type: 'user' },
        timestamp: Date.now(),
        prevEventHash: getLatestHash(),
      }];
    // ... etc
  }
}

// The projector builds the current state
function project(events: Event[]): PostState {
  return events.reduce((state, event) => {
    switch (event.type) {
      case 'post.created': return { ...state, ...event.data, status: 'active' };
      case 'post.updated': return { ...state, ...event.data };
      case 'post.deleted': return { ...state, status: 'deleted' };
    }
  }, {});
}
```

## Snapshotting

The event log grows unbounded. After N events, snapshot the
state + truncate old events:

```ts
// Every 1000 events, snapshot
async function maybeSnapshot(aggregateId: string, env: Env): Promise<void> {
  const events = await getEvents(aggregateId, env);
  if (events.length % 1000 !== 0) return;
  const state = project(events);
  await env.DB!.prepare(
    `INSERT INTO snapshots (aggregate_id, state, last_event_id, created_at)
     VALUES (?, ?, ?, ?)`
  ).bind(aggregateId, JSON.stringify(state), events[events.length - 1].id, Date.now()).run();
}
```

## CQRS (Command Query Responsibility Segregation)

Often paired with event sourcing:
- **Write side:** command handlers produce events
- **Read side:** projections (denormalized views) built from
  events

This is a separate architecture decision; not always needed.

## Verification
- **Test:** `test/event-sourcing.test.ts > replay produces same
  state` — passes
- **Live:** Audit trail is complete + time-travel query works
- **Audit:** Annual review of event store + projection

## Gotchas
- **Event schema evolution is hard.** Adding a field to an event
  type means handling old events without that field. Use
  schema versioning (event_type + event_version).
- **The "current state" query can be slow** if you replay all
  events every time. Use snapshots.
- **The event store IS the source of truth.** The projections
  are derived. If they get out of sync, replay from the event
  store.
- **Event handlers must be idempotent.** If a handler runs
  twice, it should produce the same result. (E.g. "send email
  for this event" → check if already sent.)
- **Privacy + event sourcing:** Events are PII. Treat them like
  any other PII (encryption, access control, retention policy).

## Related
- `audit-chain-durable-object.md` (event sourcing + Merkle
  chain)
- `patterns/soft-delete-pattern.md` (an event is a soft delete)
- Martin Fowler: https://martinfowler.com/eaaDev/EventSourcing.html
- CQRS: https://martinfowler.com/bliki/CQRS.html
