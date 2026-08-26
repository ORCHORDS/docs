# Snapshot Pattern: Durable Objects State Versioning

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Durable Object accumulates state mutations over time (an order workflow, a collaborative document, a game session). You need to:
- Roll back to a known-good state when a bug corrupts data
- Audit what the state looked like at a specific point in time
- Implement undo/redo for users
- Migrate state shape without losing history

Without snapshots you can only read the current state. Any corruption is permanent until manually repaired.

---

## Context

Durable Objects provide a strongly-consistent key/value store (`this.ctx.storage`). The snapshot pattern periodically (or on-demand) serialises the entire logical state into a single immutable record keyed by version number. Snapshots are stored inside the same DO storage (cheap, co-located) and optionally archived to R2 for long-term retention.

The DO remains the single source of truth. Snapshots are side-car records; the live state key is always `state:current`. Restoring means writing a snapshot back to `state:current`.

```
storage keys:
  state:current          → { version: 42, data: {...}, ts: "..." }
  snapshot:42            → { version: 42, data: {...}, ts: "..." }
  snapshot:41            → { version: 41, data: {...}, ts: "..." }
  snapshot:index         → [42, 41, 39, ...]   (ring buffer of N recent)
```

---

## Durable Object Base Class

```typescript
// src/snapshottable-do.ts
const MAX_SNAPSHOTS = 20;

export interface VersionedState<T> {
  version: number;
  data: T;
  ts: string;
}

export class SnapshottableDO<T extends Record<string, unknown>> {
  protected state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  protected async readCurrent(): Promise<VersionedState<T> | null> {
    return (await this.state.storage.get<VersionedState<T>>("state:current")) ?? null;
  }

  protected async writeCurrent(data: T): Promise<VersionedState<T>> {
    const prev = await this.readCurrent();
    const version = (prev?.version ?? 0) + 1;
    const next: VersionedState<T> = { version, data, ts: new Date().toISOString() };

    // Atomic: write current + snapshot + update index
    await this.state.storage.transaction(async (txn) => {
      txn.put("state:current", next);
      txn.put(`snapshot:${version}`, next);
      await this.updateIndex(txn, version);
    });

    return next;
  }

  private async updateIndex(
    txn: DurableObjectTransaction,
    version: number
  ): Promise<void> {
    const index: number[] =
      (await this.state.storage.get<number[]>("snapshot:index")) ?? [];
    index.unshift(version);
    if (index.length > MAX_SNAPSHOTS) {
      const evicted = index.splice(MAX_SNAPSHOTS);
      for (const v of evicted) {
        txn.delete(`snapshot:${v}`);
      }
    }
    txn.put("snapshot:index", index);
  }

  async listSnapshots(): Promise<Array<{ version: number; ts: string }>> {
    const index: number[] =
      (await this.state.storage.get<number[]>("snapshot:index")) ?? [];
    const snapshots = await Promise.all(
      index.map((v) =>
        this.state.storage.get<VersionedState<T>>(`snapshot:${v}`)
      )
    );
    return snapshots
      .filter(Boolean)
      .map((s) => ({ version: s!.version, ts: s!.ts }));
  }

  async restoreSnapshot(version: number): Promise<VersionedState<T> | null> {
    const snap = await this.state.storage.get<VersionedState<T>>(
      `snapshot:${version}`
    );
    if (!snap) return null;

    // Restore writes a new version so history is preserved (non-destructive)
    return this.writeCurrent({ ...snap.data });
  }

  async getSnapshot(version: number): Promise<VersionedState<T> | null> {
    return (
      (await this.state.storage.get<VersionedState<T>>(`snapshot:${version}`)) ??
      null
    );
  }
}
```

---

## Concrete Durable Object: Order Workflow

```typescript
// src/order-do.ts
import { SnapshottableDO, VersionedState } from "./snapshottable-do";

interface OrderState {
  orderId: string;
  status: "pending" | "confirmed" | "shipped" | "delivered" | "cancelled";
  items: Array<{ sku: string; qty: number; price: number }>;
  total: number;
}

export class OrderDO extends SnapshottableDO<OrderState> {
  constructor(state: DurableObjectState, _env: unknown) {
    super(state);
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    switch (`${request.method} ${url.pathname}`) {
      case "GET /state":
        return Response.json(await this.readCurrent());

      case "POST /transition": {
        const { status } = await request.json<{ status: OrderState["status"] }>();
        const current = await this.readCurrent();
        if (!current) return new Response("Not found", { status: 404 });

        const updated = await this.writeCurrent({ ...current.data, status });
        return Response.json(updated);
      }

      case "GET /snapshots":
        return Response.json(await this.listSnapshots());

      case "GET /snapshot": {
        const v = Number(url.searchParams.get("version"));
        const snap = await this.getSnapshot(v);
        return snap
          ? Response.json(snap)
          : new Response("Snapshot not found", { status: 404 });
      }

      case "POST /restore": {
        const { version } = await request.json<{ version: number }>();
        const restored = await this.restoreSnapshot(version);
        return restored
          ? Response.json(restored)
          : new Response("Snapshot not found", { status: 404 });
      }

      default:
        return new Response("Not found", { status: 404 });
    }
  }
}
```

---

## Archiving Old Snapshots to R2

```typescript
// Archive snapshots older than N versions to R2 for cheap long-term storage
async function archiveToR2(
  storage: DurableObjectStorage,
  bucket: R2Bucket,
  objectId: string
): Promise<void> {
  const index: number[] =
    (await storage.get<number[]>("snapshot:index")) ?? [];

  // Archive everything beyond the hot window
  const toArchive = index.slice(MAX_SNAPSHOTS);
  for (const version of toArchive) {
    const snap = await storage.get(`snapshot:${version}`);
    if (snap) {
      await bucket.put(
        `snapshots/${objectId}/v${version}.json`,
        JSON.stringify(snap),
        { httpMetadata: { contentType: "application/json" } }
      );
      await storage.delete(`snapshot:${version}`);
    }
  }
}
```

---

## HTTP Gateway Worker

```typescript
// src/worker.ts
export interface Env {
  ORDER_DO: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const orderId = url.searchParams.get("orderId");
    if (!orderId) return new Response("Missing orderId", { status: 400 });

    const id = env.ORDER_DO.idFromName(orderId);
    const stub = env.ORDER_DO.get(id);
    return stub.fetch(request);
  },
};
```

---

## Anti-patterns

- **Storing entire event log instead of periodic snapshots**: Event sourcing is a valid pattern (`event-sourcing-cloudflare-workers-d1.md`) but DO storage has a 128 KB per-value limit. A snapshot of current state is often far smaller than a full event log.
- **Snapshotting outside a transaction**: Writing `state:current` and `snapshot:N` in two separate `put()` calls means a crash between them leaves them inconsistent. Always use `storage.transaction()`.
- **Growing the snapshot index unboundedly**: Without a ring-buffer eviction strategy, the index array grows forever and hits the 128 KB storage value limit.
- **Restoring by mutating a snapshot key in place**: A restore should write a new version so the undo action itself is auditable and reversible.
- **Using version numbers as security tokens**: Version numbers are sequential and guessable. Add an authorization check before serving or restoring any snapshot.

---

## Gotchas

- `DurableObjectTransaction` does not support `list()`. Read the snapshot index before starting the transaction if you need it inside.
- DO storage `transaction()` is optimistic; it retries automatically on conflicts but can loop indefinitely under heavy contention. Keep transactions short.
- The 128 KB per-value limit applies to each stored value. For large state objects, compress with a streaming encoder or split into sub-keys and snapshot a manifest.
- Alarm-based periodic snapshots (`this.ctx.storage.setAlarm()`) are useful for time-based snapshots but alarms are not re-entrant—only one alarm fires at a time per DO instance.
- Restoring from R2 requires fetching the archive file and calling `writeCurrent()`, which creates a new version in the hot storage ring.

---

## Verification

1. Create an order, transition it through three statuses, and confirm `GET /snapshots` lists three versions.
2. Restore to version 1 and confirm `GET /state` returns the version-1 data under a new (higher) version number.
3. Write more than `MAX_SNAPSHOTS` versions and confirm older keys are absent from DO storage (check `storage.list()`).
4. Kill the Worker mid-transaction (use a deliberate throw) and confirm `state:current` and `snapshot:N` are either both present or both absent—never in a partial state.
5. Confirm that requesting a non-existent snapshot version returns 404, not a 500.

---

## Related

- `event-sourcing-cloudflare-workers-d1.md` — full event-log alternative
- `distributed-lock-durable-objects.md` — coordinating mutations across DO instances
- `per-tenant-durable-object.md` — isolating state per customer
- `saga-pattern-multi-step-workers.md` — compensating transactions for multi-step flows

---

## Sources

- Cloudflare Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Durable Objects transactions: https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/
- Snapshot pattern (Martin Fowler): https://martinfowler.com/eaaDev/Snapshot.html
