# event-sourcing-cloudflare-workers-d1

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

A compliance audit requests the complete history of every plan
change, permission grant, and content edit for the past 18 months.
The example project database stores only current state. The audit log is a
separate table with a human-readable string and no structured
payload. The diff between states cannot be reconstructed. The
auditors escalate.

Separately: a mobile user edits a playlist while offline. When they
reconnect, the app sends all pending mutations. Without an
event log the server cannot tell which write wins — last-write wins
produces corrupted ordering.

## Context

example project runs on Cloudflare Pages + Workers with D1 as the primary
datastore. D1 is SQLite-compatible, append-friendly, and lives at
the edge. It is an excellent event store for entities with <100k
events. For aggregate event counts above that, combine D1 events
with D1-backed snapshots to keep read latency bounded.

Event sourcing on Workers means: every mutation is a Worker
invocation that appends an event row and invalidates the projection
cache. Reads serve a projection — a denormalised current-state view
built from accumulated events.

## D1 Schema

```sql
-- Append-only event log
CREATE TABLE IF NOT EXISTS events (
  id           TEXT    NOT NULL PRIMARY KEY,  -- UUID
  aggregate_id TEXT    NOT NULL,              -- e.g. "playlist:abc123"
  aggregate_type TEXT  NOT NULL,              -- "playlist", "user", "subscription"
  event_type   TEXT    NOT NULL,              -- "playlist.track_added"
  payload      TEXT    NOT NULL,              -- JSON
  actor_id     TEXT    NOT NULL,
  actor_type   TEXT    NOT NULL DEFAULT 'user',  -- 'user' | 'system' | 'worker'
  seq          INTEGER NOT NULL,              -- monotonic per aggregate
  created_at   INTEGER NOT NULL              -- epoch ms
);

-- Uniqueness: one seq per aggregate (prevents duplicate appends)
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_aggregate_seq
  ON events (aggregate_id, seq);

-- Fast range reads for projection rebuild
CREATE INDEX IF NOT EXISTS idx_events_aggregate_created
  ON events (aggregate_id, created_at);

-- Snapshot table for large aggregates
CREATE TABLE IF NOT EXISTS event_snapshots (
  aggregate_id TEXT    NOT NULL PRIMARY KEY,
  state        TEXT    NOT NULL,   -- JSON projected state
  last_seq     INTEGER NOT NULL,
  created_at   INTEGER NOT NULL
);
```

## Appending Events in a Worker

```ts
interface DomainEvent {
  id: string;
  aggregateId: string;
  aggregateType: string;
  eventType: string;
  payload: unknown;
  actorId: string;
  actorType: 'user' | 'system' | 'worker';
  seq: number;
  createdAt: number;
}

async function appendEvent(
  env: Env,
  event: Omit<DomainEvent, 'id' | 'createdAt'>,
): Promise<DomainEvent> {
  const full: DomainEvent = {
    ...event,
    id: crypto.randomUUID(),
    createdAt: Date.now(),
  };
  // INSERT OR IGNORE is idempotent — safe to retry
  await env.DB.prepare(`
    INSERT OR IGNORE INTO events
      (id, aggregate_id, aggregate_type, event_type, payload, actor_id, actor_type, seq, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    full.id,
    full.aggregateId,
    full.aggregateType,
    full.eventType,
    JSON.stringify(full.payload),
    full.actorId,
    full.actorType,
    full.seq,
    full.createdAt,
  ).run();
  return full;
}
```

`INSERT OR IGNORE` on the `(aggregate_id, seq)` unique index makes
appends idempotent — a retried Worker that already wrote seq=42
will silently skip the duplicate.

## Projection Rebuild

A projection is a plain TypeScript reducer over the event stream:

```ts
interface PlaylistState {
  id: string;
  name: string;
  tracks: string[];
  isPublic: boolean;
  deletedAt: number | null;
}

type PlaylistEvent =
  | { eventType: 'playlist.created'; payload: { name: string; isPublic: boolean } }
  | { eventType: 'playlist.renamed'; payload: { name: string } }
  | { eventType: 'playlist.track_added'; payload: { trackId: string } }
  | { eventType: 'playlist.track_removed'; payload: { trackId: string } }
  | { eventType: 'playlist.deleted'; payload: Record<string, never> };

function reducePlaylist(events: DomainEvent[]): PlaylistState {
  return events.reduce<PlaylistState>(
    (state, ev) => {
      const e = ev as PlaylistEvent & { aggregateId: string };
      switch (e.eventType) {
        case 'playlist.created':
          return { ...state, id: ev.aggregateId, ...e.payload, tracks: [], deletedAt: null };
        case 'playlist.renamed':
          return { ...state, name: e.payload.name };
        case 'playlist.track_added':
          return { ...state, tracks: [...state.tracks, e.payload.trackId] };
        case 'playlist.track_removed':
          return { ...state, tracks: state.tracks.filter(t => t !== e.payload.trackId) };
        case 'playlist.deleted':
          return { ...state, deletedAt: Date.now() };
        default:
          return state;
      }
    },
    { id: '', name: '', tracks: [], isPublic: false, deletedAt: null },
  );
}

async function loadPlaylist(env: Env, playlistId: string): Promise<PlaylistState> {
  // Load from snapshot first
  const snap = await env.DB.prepare(
    `SELECT state, last_seq FROM event_snapshots WHERE aggregate_id = ?`
  ).bind(playlistId).first<{ state: string; last_seq: number }>();

  const afterSeq = snap ? snap.last_seq : -1;
  const baseState: PlaylistState = snap
    ? JSON.parse(snap.state)
    : { id: playlistId, name: '', tracks: [], isPublic: false, deletedAt: null };

  const rows = await env.DB.prepare(
    `SELECT * FROM events WHERE aggregate_id = ? AND seq > ? ORDER BY seq ASC`
  ).bind(playlistId, afterSeq).all<DomainEvent>();

  return rows.results.reduce((s, ev) => {
    const typed = { ...ev, payload: JSON.parse(ev.payload as unknown as string) };
    return reducePlaylist([typed]) === s ? s : reducePlaylist([...[baseState as any], typed]);
  }, baseState);
}
```

## Snapshotting Strategy

Rebuild from events is O(n) in event count. For long-lived
aggregates, snapshot every N events:

```ts
const SNAPSHOT_EVERY = 100;

async function maybeSnapshot(env: Env, aggregateId: string): Promise<void> {
  const count = await env.DB.prepare(
    `SELECT COUNT(*) as c FROM events WHERE aggregate_id = ?`
  ).bind(aggregateId).first<{ c: number }>();

  if (!count || count.c % SNAPSHOT_EVERY !== 0) return;

  const rows = await env.DB.prepare(
    `SELECT * FROM events WHERE aggregate_id = ? ORDER BY seq ASC`
  ).bind(aggregateId).all<DomainEvent>();

  const events = rows.results.map(r => ({
    ...r, payload: JSON.parse(r.payload as unknown as string),
  }));
  const state = reducePlaylist(events);
  const lastSeq = events[events.length - 1].seq;

  await env.DB.prepare(`
    INSERT INTO event_snapshots (aggregate_id, state, last_seq, created_at)
    VALUES (?, ?, ?, ?)
    ON CONFLICT (aggregate_id) DO UPDATE SET
      state = excluded.state, last_seq = excluded.last_seq, created_at = excluded.created_at
  `).bind(aggregateId, JSON.stringify(state), lastSeq, Date.now()).run();
}
```

## Mobile Offline Event Queue

Mobile clients accumulate events while offline and replay them in
order on reconnect. The server validates the sequence:

```ts
// Client sends a batch of ordered events
interface OfflineEventBatch {
  aggregateId: string;
  events: Array<{ eventType: string; payload: unknown; seq: number; clientAt: number }>;
}

export async function handleOfflineSync(req: Request, env: Env, ctx: McContext): Promise<Response> {
  const batch = await req.json<OfflineEventBatch>();
  const results: Array<{ seq: number; status: 'applied' | 'duplicate' | 'conflict' }> = [];

  for (const ev of batch.events.sort((a, b) => a.seq - b.seq)) {
    try {
      await appendEvent(env, {
        aggregateId: batch.aggregateId,
        aggregateType: 'playlist',
        eventType: ev.eventType,
        payload: ev.payload,
        actorId: ctx.user.id,
        actorType: 'user',
        seq: ev.seq,
      });
      results.push({ seq: ev.seq, status: 'applied' });
    } catch (err: any) {
      // Unique constraint violation = seq already taken
      if (err.message?.includes('UNIQUE constraint')) {
        results.push({ seq: ev.seq, status: 'duplicate' });
      } else {
        results.push({ seq: ev.seq, status: 'conflict' });
      }
    }
  }

  return Response.json({ results }, { status: 207 });
}
```

| Offline scenario              | Client seq | Server result  |
|-------------------------------|-----------|----------------|
| First sync after offline      | 5,6,7     | all applied    |
| Reconnect retry (all already) | 5,6,7     | all duplicate  |
| Conflict (seq 6 taken by web) | 6         | conflict → UI  |
| Partial (5 applied, 6 fails)  | 5,6       | mixed 207      |

## Anti-patterns

- **Mutating events.** Events are facts; once appended they are
  immutable. Corrections are new events (e.g. `track_removed`
  after a wrong `track_added`).
- **Business logic in the projector.** The reducer only reads
  events; it must not call external services or have side effects.
- **Unbounded event replay without snapshots.** An aggregate with
  50k events rebuilds slowly. Snapshot aggressively for write-heavy
  aggregates.
- **Missing aggregate type column.** Without `aggregate_type`, a
  global event stream query becomes an expensive table scan.
- **Storing PII in event payloads without encryption.** Events
  persist indefinitely. Encrypt PII fields or replace with
  references to a separate PII store.

## Gotchas

- D1 has a 1MB row limit. Payloads with binary data (images,
  blobs) must be stored in R2; events reference the R2 key.
- `seq` must be monotonic per aggregate, not global. Use the
  current max(seq)+1 inside a D1 transaction to avoid gaps
  under concurrent writers. A DO per aggregate guarantees
  serialised seq assignment.
- Replaying all events on every read defeats the purpose of
  snapshotting. Cache projections in KV with a short TTL and
  invalidate on new event append.
- Event schema evolves. Use an `event_version` column from day
  one. Projectors must handle v1 and v2 of the same event type.

## Verification

```bash
# Append a test event
curl -s -X POST https://api.example.com/v1/playlists/pl_test/events \
  -H "Content-Type: application/json" \
  -d '{"eventType":"playlist.track_added","payload":{"trackId":"t_123"}}'

# Load projection
curl -s https://api.example.com/v1/playlists/pl_test | jq '.tracks'
# Expect: ["t_123"]

# Replay check: query raw events
wrangler d1 execute DB --command \
  "SELECT event_type, seq, created_at FROM events WHERE aggregate_id='playlist:pl_test' ORDER BY seq"
```

## Related

- `event-sourcing.md` — generic pattern decision guide
- `saga-pattern-multi-step-workers.md` — sagas produce events
- `idempotency-key-pattern-workers-d1.md` — idempotent event appends
- `per-tenant-durable-object.md` — DO for serialised seq assignment

## Sources

- Martin Fowler, Event Sourcing: https://martinfowler.com/eaaDev/EventSourcing.html
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Greg Young, CQRS and Event Sourcing: https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf
