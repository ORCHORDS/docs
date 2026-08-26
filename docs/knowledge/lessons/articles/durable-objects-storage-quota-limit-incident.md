# Durable Objects Storage Quota Limit Incident

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A collaborative document editor backed by Durable Objects began returning 500 errors for
all writes to documents older than 60 days. `this.ctx.storage.put()` threw
`Error: Storage quota exceeded`. Only new documents (< 60 days old, assigned to recently
created DO instances) continued to work. The root cause was unbounded append-only storage:
every keystroke delta was persisted without any compaction or TTL, filling the per-DO
storage limit of 128 KB for thousands of high-activity document objects.

## Context

Each Durable Object instance has a storage limit of **128 KB of key-value storage** (as of
2026; check current docs for updates). This limit applies per DO instance, not per class
or account. A pattern where every event is appended as a new key (`delta:${Date.now()}`)
grows without bound. Because DO storage is synchronous and deterministic within a single
object, writes that would exceed the quota throw synchronously and there is no partial
write or overflow behaviour. The error surfaced as a 500 to the client because the DO
class had no quota-aware write path or compaction strategy.

## Enforce a Maximum Key Count Before Writing

Before every `put()`, check the number of stored keys and refuse or compact when near the
limit. A synchronous pre-check is safe because DO instances are single-threaded.

```typescript
// src/document-do.ts
export class DocumentDO implements DurableObject {
  private readonly MAX_KEYS = 500; // empirically safe given average value sizes

  constructor(private readonly ctx: DurableObjectState) {}

  async fetch(request: Request): Promise<Response> {
    if (request.method === 'POST') {
      return this.handleWrite(request);
    }
    return new Response('not found', { status: 404 });
  }

  private async handleWrite(request: Request): Promise<Response> {
    const keys = await this.ctx.storage.list({ limit: this.MAX_KEYS + 1 });
    if (keys.size >= this.MAX_KEYS) {
      await this.compact();
    }
    const delta = await request.json<{ ts: number; op: string }>();
    await this.ctx.storage.put(`delta:${delta.ts}`, delta);
    return new Response('ok');
  }

  private async compact(): Promise<void> {
    // Merge all deltas into a single snapshot, delete individual delta keys
    const all = await this.ctx.storage.list<{ ts: number; op: string }>();
    const snapshot = { ops: [...all.values()], compactedAt: Date.now() };
    await this.ctx.storage.put('snapshot', snapshot);
    const deltaKeys = [...all.keys()].filter((k) => k.startsWith('delta:'));
    await this.ctx.storage.delete(deltaKeys);
  }
}
```

## Use Alarms to Trigger Proactive Compaction

Waiting until write time to compact is reactive. Schedule a DO alarm to compact during
off-peak hours before quota pressure occurs.

```typescript
// src/document-do.ts (alarm addition)
async alarm(): Promise<void> {
  const keys = await this.ctx.storage.list({ limit: 1, prefix: 'delta:' });
  if (keys.size > 0) {
    await this.compact();
  }
  // Reschedule for next night
  await this.ctx.storage.setAlarm(Date.now() + 24 * 60 * 60 * 1000);
}

// Ensure alarm is set when the DO first receives traffic
private async ensureAlarmScheduled(): Promise<void> {
  const existing = await this.ctx.storage.getAlarm();
  if (existing === null) {
    await this.ctx.storage.setAlarm(Date.now() + 60_000);
  }
}
```

## Track Storage Pressure as a Custom Metric

Emit a metric with the key count after every write so you can alert before the limit is
hit rather than after writes start failing.

```typescript
// src/document-do.ts (metrics addition)
private async emitStorageMetric(keyCount: number): Promise<void> {
  // Works with Workers Analytics Engine binding
  // Requires [[analytics_engine_datasets]] in wrangler.toml
  if (this.env?.ANALYTICS) {
    this.env.ANALYTICS.writeDataPoint({
      blobs: [this.ctx.id.toString()],
      doubles: [keyCount],
      indexes: ['do_storage_key_count'],
    });
  }
}
```

## Offload Large Values to R2 or KV

When individual values are large (images, compiled documents, binary blobs) the 128 KB
quota is exhausted extremely quickly. Store only references in DO storage; put the data
in R2 or KV.

```typescript
// src/document-do.ts (large-value pattern)
private async writeLargeValue(key: string, data: ArrayBuffer): Promise<void> {
  const r2Key = `do-overflow/${this.ctx.id.toString()}/${key}`;
  await this.env.BUCKET.put(r2Key, data);
  // Store only the reference in DO storage (< 100 bytes)
  await this.ctx.storage.put(key, { r2Key, size: data.byteLength });
}

private async readLargeValue(key: string): Promise<ArrayBuffer | null> {
  const ref = await this.ctx.storage.get<{ r2Key: string }>(key);
  if (!ref) return null;
  const obj = await this.env.BUCKET.get(ref.r2Key);
  return obj ? obj.arrayBuffer() : null;
}
```

## Graceful Quota Error Response

When quota is exceeded despite guards (e.g., a compaction bug), return a structured error
response instead of an unhandled 500, and emit an alert.

```typescript
// src/document-do.ts (error boundary)
async fetch(request: Request): Promise<Response> {
  try {
    return await this.handleWrite(request);
  } catch (err) {
    const msg = (err as Error).message ?? '';
    if (msg.includes('Storage quota exceeded')) {
      console.error('DO storage quota exceeded', { id: this.ctx.id.toString() });
      return Response.json({ error: 'storage_quota_exceeded' }, { status: 507 });
    }
    throw err;
  }
}
```

## Anti-patterns

- Append-only key patterns (`event:${Date.now()}`) with no compaction or deletion — the
  keyspace grows without bound until the quota is hit.
- Storing large binary values directly in DO storage rather than referencing them from R2.
- No pre-write quota check — the only signal of impending quota exhaustion is a thrown
  error in production.
- Ignoring `ctx.storage.getAlarm()` when scheduling alarms — scheduling a second alarm
  without checking cancels the existing one silently.

## Gotchas

- `this.ctx.storage.list()` with no options returns all keys up to the DO storage limit;
  always pass `limit` to avoid reading the entire key space on every write.
- DO storage limits are per-instance, not per namespace or account; a single high-traffic
  DO can hit the quota while other instances remain healthy.
- Deleting keys frees quota immediately; compaction during a write is safe and synchronous.
- Alarms fire even if no HTTP request has arrived; they run inside the DO's event loop and
  have access to storage just like a fetch handler.
- `storage.delete(keys)` accepts an array; calling it in a loop with single keys is 10x
  slower than passing the full array.

## Verification

1. Write a Vitest + Miniflare test that fills 501 keys in a DO instance and asserts
   `compact()` is called and key count drops below `MAX_KEYS` after the next write.
2. Deploy a staging DO and confirm the alarm fires within 65 seconds of first write.
3. Confirm the Analytics Engine metric appears in the dashboard within 60 seconds of a
   write that triggers compaction.
4. Force a quota exceeded error in staging by disabling compaction and filling storage;
   verify the client receives HTTP 507 and the error is logged with the DO id.

## Related

- `durable-object-alarm-silent-failure-payment-reminders.md`
- `durable-objects-websocket-hibernation-migration-adr.md`
- `cloudflare-storage-primitive-selection.md`
- `never-delete-without-soft-delete-first.md`

## Sources

- Cloudflare Durable Objects documentation — storage API and limits (2026)
- Cloudflare Blog: "Durable Objects: now with a long-awaited feature" (2023)
- Internal postmortem: example.com document editor storage incident, Q1 2026
- Cloudflare Community: "Durable Object storage quota exceeded" thread
