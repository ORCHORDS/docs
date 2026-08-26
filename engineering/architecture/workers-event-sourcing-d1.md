# Event Sourcing with D1 as the Event Store on Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a full audit trail of every change to an aggregate (e.g., an order, a cart, a user account). Traditional `UPDATE` statements destroy history. Debugging production issues is painful because you cannot replay what happened. You want the ability to reconstruct any past state, replay events for new projections, and enforce optimistic concurrency control without distributed locks.

---

## Context

Event Sourcing stores **all changes as an immutable, append-only sequence of domain events**. The current state of an aggregate is derived by replaying its events from the beginning (or from a snapshot). D1 is a natural fit:

- Its SQL interface supports `INSERT`-only writes with `sequence` checks.
- `SELECT … ORDER BY sequence` replays the stream.
- Snapshots stored in a separate table avoid full replays on large aggregates.
- Projections live in derived tables (or KV — see `workers-cqrs-pattern-d1-kv.md`).

---

## Solution

```typescript
// ============================================================
// types.ts
// ============================================================
export type OrderStatus = 'PENDING' | 'CONFIRMED' | 'SHIPPED' | 'CANCELLED';

export interface OrderItem {
  productId: string;
  quantity: number;
  unitPrice: number; // cents
}

export interface OrderState {
  id: string;
  customerId: string;
  items: OrderItem[];
  status: OrderStatus;
  totalCents: number;
}

// ---- Events ----
export interface OrderCreated {
  type: 'ORDER_CREATED';
  customerId: string;
  items: OrderItem[];
}
export interface ItemAdded {
  type: 'ITEM_ADDED';
  item: OrderItem;
}
export interface OrderConfirmed {
  type: 'ORDER_CONFIRMED';
}
export interface OrderCancelled {
  type: 'ORDER_CANCELLED';
  reason: string;
}
export interface OrderShipped {
  type: 'ORDER_SHIPPED';
  trackingNumber: string;
}

export type OrderEvent =
  | OrderCreated
  | ItemAdded
  | OrderConfirmed
  | OrderCancelled
  | OrderShipped;

export interface StoredEvent {
  id: string;
  aggregateId: string;
  sequence: number;
  type: string;
  payload: string; // JSON
  occurredAt: number;
}

// ============================================================
// event-store.ts — D1-backed append-only store
// ============================================================
export class D1EventStore {
  constructor(private db: D1Database) {}

  /**
   * Append events to an aggregate's stream.
   * expectedSequence = -1 means the aggregate must not exist.
   * Throws on optimistic concurrency conflict.
   */
  async append(
    aggregateId: string,
    events: OrderEvent[],
    expectedSequence: number,
  ): Promise<number> {
    // Read current max sequence inside the same Worker invocation.
    const row = await this.db
      .prepare('SELECT COALESCE(MAX(sequence), -1) AS seq FROM events WHERE aggregate_id = ?1')
      .bind(aggregateId)
      .first<{ seq: number }>();

    const currentSeq = row?.seq ?? -1;

    if (currentSeq !== expectedSequence) {
      throw new ConcurrencyError(
        `Concurrency conflict on ${aggregateId}: expected seq ${expectedSequence}, got ${currentSeq}`,
      );
    }

    const stmts = events.map((event, i) => {
      const seq = expectedSequence + 1 + i;
      return this.db
        .prepare(
          `INSERT INTO events (id, aggregate_id, sequence, type, payload, occurred_at)
           VALUES (?1, ?2, ?3, ?4, ?5, ?6)`,
        )
        .bind(
          crypto.randomUUID(),
          aggregateId,
          seq,
          event.type,
          JSON.stringify(event),
          Date.now(),
        );
    });

    await this.db.batch(stmts);

    return expectedSequence + events.length;
  }

  /** Load all events for an aggregate, optionally from a given sequence. */
  async load(aggregateId: string, fromSequence = 0): Promise<StoredEvent[]> {
    const { results } = await this.db
      .prepare(
        `SELECT id, aggregate_id, sequence, type, payload, occurred_at
         FROM events
         WHERE aggregate_id = ?1 AND sequence >= ?2
         ORDER BY sequence ASC`,
      )
      .bind(aggregateId, fromSequence)
      .all<StoredEvent>();
    return results;
  }

  /** Load a full slice of the global event stream (for projections). */
  async loadGlobal(afterId: string | null, limit = 100): Promise<StoredEvent[]> {
    const query = afterId
      ? `SELECT * FROM events WHERE id > ?1 ORDER BY occurred_at ASC LIMIT ?2`
      : `SELECT * FROM events ORDER BY occurred_at ASC LIMIT ?1`;
    const stmt = afterId
      ? this.db.prepare(query).bind(afterId, limit)
      : this.db.prepare(query).bind(limit);
    const { results } = await stmt.all<StoredEvent>();
    return results;
  }
}

export class ConcurrencyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ConcurrencyError';
  }
}

// ============================================================
// snapshot-store.ts
// ============================================================
export interface Snapshot<T> {
  aggregateId: string;
  sequence: number;
  state: T;
  takenAt: number;
}

export class D1SnapshotStore {
  constructor(private db: D1Database) {}

  async save<T>(snapshot: Snapshot<T>): Promise<void> {
    await this.db
      .prepare(
        `INSERT INTO snapshots (aggregate_id, sequence, state, taken_at)
         VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT (aggregate_id) DO UPDATE
           SET sequence = excluded.sequence,
               state    = excluded.state,
               taken_at = excluded.taken_at`,
      )
      .bind(
        snapshot.aggregateId,
        snapshot.sequence,
        JSON.stringify(snapshot.state),
        snapshot.takenAt,
      )
      .run();
  }

  async load<T>(aggregateId: string): Promise<Snapshot<T> | null> {
    const row = await this.db
      .prepare('SELECT * FROM snapshots WHERE aggregate_id = ?1')
      .bind(aggregateId)
      .first<{ aggregate_id: string; sequence: number; state: string; taken_at: number }>();
    if (!row) return null;
    return {
      aggregateId: row.aggregate_id,
      sequence: row.sequence,
      state: JSON.parse(row.state) as T,
      takenAt: row.taken_at,
    };
  }
}

// ============================================================
// order-aggregate.ts — state reconstruction
// ============================================================
export class OrderAggregate {
  private state: OrderState | null = null;
  private sequence = -1;

  static reconstitute(events: StoredEvent[]): OrderAggregate {
    const agg = new OrderAggregate();
    for (const stored of events) {
      agg.apply(JSON.parse(stored.payload) as OrderEvent, stored.sequence);
    }
    return agg;
  }

  static fromSnapshot(snapshot: Snapshot<OrderState>): OrderAggregate {
    const agg = new OrderAggregate();
    agg.state = snapshot.state;
    agg.sequence = snapshot.sequence;
    return agg;
  }

  private apply(event: OrderEvent, seq: number): void {
    this.sequence = seq;
    switch (event.type) {
      case 'ORDER_CREATED':
        this.state = {
          id: '', // set externally via aggregateId
          customerId: event.customerId,
          items: event.items,
          status: 'PENDING',
          totalCents: event.items.reduce((s, i) => s + i.quantity * i.unitPrice, 0),
        };
        break;
      case 'ITEM_ADDED':
        if (this.state) {
          this.state.items.push(event.item);
          this.state.totalCents += event.item.quantity * event.item.unitPrice;
        }
        break;
      case 'ORDER_CONFIRMED':
        if (this.state) this.state.status = 'CONFIRMED';
        break;
      case 'ORDER_CANCELLED':
        if (this.state) this.state.status = 'CANCELLED';
        break;
      case 'ORDER_SHIPPED':
        if (this.state) this.state.status = 'SHIPPED';
        break;
    }
  }

  get currentState(): OrderState | null { return this.state; }
  get currentSequence(): number { return this.sequence; }

  // --- Command methods that return new events ---
  createOrder(id: string, customerId: string, items: OrderItem[]): OrderEvent[] {
    if (this.state) throw new Error('Order already exists');
    return [{ type: 'ORDER_CREATED', customerId, items }];
  }

  confirmOrder(): OrderEvent[] {
    if (!this.state || this.state.status !== 'PENDING') {
      throw new Error('Order must be PENDING to confirm');
    }
    return [{ type: 'ORDER_CONFIRMED' }];
  }
}

// ============================================================
// order-service.ts — orchestrates store + aggregate
// ============================================================
const SNAPSHOT_INTERVAL = 20; // take snapshot every 20 events

export class OrderService {
  constructor(
    private store: D1EventStore,
    private snapshots: D1SnapshotStore,
  ) {}

  async load(orderId: string): Promise<OrderAggregate> {
    const snapshot = await this.snapshots.load<OrderState>(orderId);
    let agg: OrderAggregate;
    let fromSeq = 0;

    if (snapshot) {
      agg = OrderAggregate.fromSnapshot(snapshot);
      fromSeq = snapshot.sequence + 1;
    } else {
      agg = new OrderAggregate();
    }

    const events = await this.store.load(orderId, fromSeq);
    const full = OrderAggregate.fromSnapshot(
      snapshot ?? { aggregateId: orderId, sequence: -1, state: null as unknown as OrderState, takenAt: 0 },
    );
    // Re-hydrate from snapshot + remaining events
    const rehydrated = snapshot ? OrderAggregate.fromSnapshot(snapshot) : new OrderAggregate();
    for (const ev of events) {
      (rehydrated as unknown as { apply: (e: OrderEvent, seq: number) => void }).apply(
        JSON.parse(ev.payload),
        ev.sequence,
      );
    }
    return rehydrated;
  }

  async save(orderId: string, agg: OrderAggregate, newEvents: OrderEvent[]): Promise<void> {
    const newSeq = await this.store.append(orderId, newEvents, agg.currentSequence);

    if (newSeq % SNAPSHOT_INTERVAL === 0 && agg.currentState) {
      await this.snapshots.save({
        aggregateId: orderId,
        sequence: newSeq,
        state: agg.currentState,
        takenAt: Date.now(),
      });
    }
  }
}

// ============================================================
// worker.ts
// ============================================================
interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const store = new D1EventStore(env.DB);
    const snapshots = new D1SnapshotStore(env.DB);
    const service = new OrderService(store, snapshots);
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/orders') {
      const body = await request.json<{ customerId: string; items: OrderItem[] }>();
      const orderId = crypto.randomUUID();
      const agg = new OrderAggregate();
      const events = agg.createOrder(orderId, body.customerId, body.items);
      await store.append(orderId, events, -1);
      return Response.json({ orderId }, { status: 201 });
    }

    if (request.method === 'POST' && url.pathname.endsWith('/confirm')) {
      const orderId = url.pathname.split('/')[2];
      const agg = await service.load(orderId);
      const events = agg.confirmOrder();
      await service.save(orderId, agg, events);
      return Response.json({ ok: true });
    }

    if (request.method === 'GET' && url.pathname.startsWith('/orders/')) {
      const orderId = url.pathname.split('/')[2];
      const agg = await service.load(orderId);
      return agg.currentState
        ? Response.json(agg.currentState)
        : Response.json({ error: 'not found' }, { status: 404 });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Implementation Details

**D1 Schema**

```sql
CREATE TABLE IF NOT EXISTS events (
  id           TEXT    PRIMARY KEY,
  aggregate_id TEXT    NOT NULL,
  sequence     INTEGER NOT NULL,
  type         TEXT    NOT NULL,
  payload      TEXT    NOT NULL,
  occurred_at  INTEGER NOT NULL,
  UNIQUE (aggregate_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events (aggregate_id, sequence);

CREATE TABLE IF NOT EXISTS snapshots (
  aggregate_id TEXT    PRIMARY KEY,
  sequence     INTEGER NOT NULL,
  state        TEXT    NOT NULL,
  taken_at     INTEGER NOT NULL
);
```

The `UNIQUE (aggregate_id, sequence)` constraint is the database-level guard for the optimistic concurrency check. Two concurrent Workers racing to append sequence `5` will both succeed in the application-level sequence check (both read `4`) but only one D1 `INSERT` will win — the other throws a constraint error that bubbles up as a 409.

**Snapshot threshold** — 20 events is conservative. For large aggregates, tune down to 10. For simple aggregates with < 100 lifetime events, snapshots may not be needed.

---

## Anti-patterns

- **Mutating events** — Events are immutable facts. Never `UPDATE` the events table. Corrections are new events (e.g., `PRICE_CORRECTION_APPLIED`).
- **Storing current state in the events table** — Keep the events table purely append-only. Derived state belongs in projections or snapshot tables.
- **Loading the full stream without snapshots** — A 10,000-event order will time out. Always implement snapshots.
- **Using wall-clock time as sort order** — Two events with the same millisecond timestamp can arrive out of order. Always sort by `sequence`, not `occurred_at`.

---

## Gotchas

- D1 does not support stored procedures or triggers. The optimistic concurrency check (read max sequence, then insert) is not atomic at the SQL level. Rely on the `UNIQUE` constraint as the atomic guard.
- `db.batch()` executes statements in order but does not guarantee a single SQL transaction across all statements in all D1 plans. For true atomicity, wrap in an explicit `BEGIN`/`COMMIT` via raw SQL if D1's transaction API supports it at your plan level.
- Workers CPU time limit is 50 ms on the free plan. Replaying 1,000 events in-memory approaches this. Use snapshots aggressively on the free tier.

---

## Verification

```bash
# Create order
curl -X POST https://worker.example.com/orders \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"cust-1","items":[{"productId":"p1","quantity":2,"unitPrice":500}]}'

# Confirm order
curl -X POST https://worker.example.com/orders/<id>/confirm

# Read current state (reconstructed from events)
curl https://worker.example.com/orders/<id>

# Inspect raw event stream in D1 console
# SELECT * FROM events WHERE aggregate_id = '<id>' ORDER BY sequence;
```

---

## Related

- `workers-cqrs-pattern-d1-kv.md` — project events into KV for fast reads
- `actor-model-durable-objects.md` — Durable Objects as an alternative single-writer event store
- `graceful-degradation-feature-tiers.md` — return snapshot state when event replay is too slow

---

## Sources

- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)
- Martin Fowler, *Event Sourcing* — https://martinfowler.com/eaaDev/EventSourcing.html
- Greg Young, *CQRS and Event Sourcing* (2014)
- Vaughn Vernon, *Implementing Domain-Driven Design*, Chapter 8
