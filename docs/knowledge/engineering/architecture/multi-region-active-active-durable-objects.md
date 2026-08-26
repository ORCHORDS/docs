# Multi-Region Active-Active with Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A globally deployed SaaS application needs every region to accept writes — not just reads — without
cross-region coordination blocking the user. Users in Tokyo and São Paulo must both be able to
create documents, cast votes, or update shared state at the same time. Eventual consistency
conflicts must be detectable and resolvable deterministically, not silently lost.

## Context

Cloudflare Durable Objects are globally addressable but physically pinned to one Cloudflare region
at creation time (or explicitly via `locationHint`). True active-active at the application level
is therefore not a single-DO problem — it requires a topology of co-ordinating actors:

- **Local DOs** accept writes in each region with low latency.
- **A Global DO** (or a small set of sharded global DOs) owns the canonical state and resolves
  conflicts.
- **CRDTs or version-vector logic** propagates updates between local and global actors
  asynchronously.

This article shows a practical pattern using last-write-wins (LWW) with hybrid logical clocks
(HLC) for simple scalar values, and an observed-remove set (OR-Set) CRDT for membership
operations, all wired through Durable Object RPC.

## Topology Overview

```
 User (Tokyo) → Tokyo Worker → Tokyo-DO ──┐
                                          ├──► Global-DO (coordinator)
 User (London) → London Worker → London-DO┘

 Global-DO replicates deltas back to local DOs via Alarm-driven reconciliation.
```

Each **Local DO** is resolved with `idFromName("local:" + region)` — one per Cloudflare region
the app targets. The **Global DO** is resolved with `idFromName("global:tenant:" + tenantId)`,
pinned via `locationHint` to the region closest to the primary datastore.

## Local DO — Accepting Writes with HLC Timestamps

```typescript
// LocalRegionDO.ts
import { HybridLogicalClock } from "./hlc";

interface Entry { value: unknown; hlc: string; }

export class LocalRegionDO implements DurableObject {
  private state: DurableObjectState;
  private data: Map<string, Entry> = new Map();
  private hlc = new HybridLogicalClock();

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const { method, key, value, remoteHlc } = await request.json<{
      method: "write" | "read" | "merge";
      key: string;
      value?: unknown;
      remoteHlc?: string;
    }>();

    if (method === "write") {
      const ts = this.hlc.now();
      this.data.set(key, { value, hlc: ts });
      await this.state.storage.put(key, { value, hlc: ts });
      // Async push to global DO
      this.state.waitUntil(this.pushToGlobal(key, value, ts));
      return Response.json({ hlc: ts });
    }

    if (method === "read") {
      const entry = this.data.get(key) ?? await this.state.storage.get<Entry>(key);
      return Response.json(entry ?? null);
    }

    if (method === "merge") {
      // Accept delta from global DO
      const existing = this.data.get(key);
      if (!existing || remoteHlc! > existing.hlc) {
        this.data.set(key, { value, hlc: remoteHlc! });
        await this.state.storage.put(key, { value, hlc: remoteHlc! });
      }
      return new Response("ok");
    }

    return new Response("unknown method", { status: 400 });
  }

  private async pushToGlobal(key: string, value: unknown, hlc: string) {
    const globalId = (this.state as any).env.GLOBAL_DO.idFromName("global:default");
    const stub = (this.state as any).env.GLOBAL_DO.get(globalId);
    await stub.fetch(new Request("https://do-internal/merge", {
      method: "POST",
      body: JSON.stringify({ key, value, hlc, source: (this.state as any).env.REGION }),
    }));
  }
}
```

## Global DO — Conflict Resolution and Fan-Out

```typescript
// GlobalDO.ts
interface VersionedEntry { value: unknown; hlc: string; region: string; }

export class GlobalDO implements DurableObject {
  private state: DurableObjectState;
  private data: Map<string, VersionedEntry> = new Map();

  constructor(state: DurableObjectState) {
    this.state = state;
    // Schedule periodic reconciliation alarm
    this.state.storage.getAlarm().then((a) => {
      if (!a) this.state.storage.setAlarm(Date.now() + 5_000);
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/merge") {
      const { key, value, hlc, source } = await request.json<{
        key: string; value: unknown; hlc: string; source: string;
      }>();
      const existing = this.data.get(key);

      // LWW: higher HLC string wins (lexicographic comparison is safe for HLC)
      if (!existing || hlc > existing.hlc) {
        const entry: VersionedEntry = { value, hlc, region: source };
        this.data.set(key, entry);
        await this.state.storage.put(key, entry);
      }
      return new Response("accepted");
    }

    if (url.pathname === "/snapshot") {
      const all: Record<string, VersionedEntry> = {};
      for (const [k, v] of this.data) all[k] = v;
      return Response.json(all);
    }

    return new Response("not found", { status: 404 });
  }

  async alarm(): Promise<void> {
    // Fan-out updated entries to all local DOs
    const regions: string[] = JSON.parse(
      await (this.state as any).env.CONFIG_KV.get("active_regions") ?? "[]"
    );
    for (const [key, entry] of this.data) {
      for (const region of regions) {
        const id = (this.state as any).env.LOCAL_DO.idFromName(`local:${region}`);
        const stub = (this.state as any).env.LOCAL_DO.get(id);
        stub.fetch(new Request("https://do-internal/", {
          method: "POST",
          body: JSON.stringify({ method: "merge", key, value: entry.value, remoteHlc: entry.hlc }),
        })).catch(() => { /* best-effort; alarm will retry */ });
      }
    }
    // Reschedule
    await this.state.storage.setAlarm(Date.now() + 5_000);
  }
}
```

## Hybrid Logical Clock Implementation

```typescript
// hlc.ts — minimal HLC for ordering across regions
export class HybridLogicalClock {
  private maxWall = 0;
  private counter = 0;

  now(): string {
    const wall = Date.now();
    if (wall > this.maxWall) {
      this.maxWall = wall;
      this.counter = 0;
    } else {
      this.counter++;
    }
    // Format: "<13-digit wall ms>-<5-digit counter>-<random tiebreak>"
    return `${String(this.maxWall).padStart(13, "0")}-${String(this.counter).padStart(5, "0")}-${Math.random().toString(36).slice(2, 8)}`;
  }

  receive(remote: string): void {
    const remoteWall = parseInt(remote.slice(0, 13), 10);
    const wall = Date.now();
    this.maxWall = Math.max(this.maxWall, remoteWall, wall);
    if (this.maxWall === remoteWall) {
      const remoteCounter = parseInt(remote.slice(14, 19), 10);
      this.counter = remoteCounter + 1;
    } else if (this.maxWall > wall) {
      this.counter++;
    } else {
      this.counter = 0;
    }
  }
}
```

`wrangler.toml`:

```toml
[[durable_objects.bindings]]
name = "LOCAL_DO"
class_name = "LocalRegionDO"

[[durable_objects.bindings]]
name = "GLOBAL_DO"
class_name = "GlobalDO"

[[migrations]]
tag = "v1"
new_classes = ["LocalRegionDO", "GlobalDO"]
```

## Anti-patterns

- **Routing all writes directly to the Global DO**: Eliminates the low-latency benefit of active-
  active. Local DOs exist precisely to absorb writes without cross-region hops.
- **Using wall-clock timestamps as the sole conflict resolver**: Two machines can have clocks
  skewed by hundreds of milliseconds. Always pair a physical timestamp with a logical counter
  (HLC) to break ties deterministically.
- **Unbounded fan-out in the alarm**: Fan out to all regions every 5 seconds means O(regions ×
  keys) fetch calls per alarm tick. Batch into a single delta snapshot per region.
- **Storing entire state in the alarm loop**: Alarms have a 30-second wall-clock budget. Only
  propagate dirty keys since the last alarm, not the full keyspace.

## Gotchas

- Durable Objects are created in the region of the first request that creates them unless a
  `locationHint` is provided. Always specify `locationHint` for the Global DO to pin it to your
  primary region.
- The `waitUntil()` push to the Global DO in the Local DO runs after the response is returned to
  the user. If the Worker isolate is evicted before it completes, the push is lost. An alarm-
  driven retry in the Local DO adds resilience.
- Durable Object storage `put()` is synchronous within a request but does not guarantee durability
  until the request completes. Do not rely on `put()` results across concurrent requests within
  the same DO — Durable Objects are single-threaded and queue fetch calls.
- Cross-DO RPC via `stub.fetch()` counts against Subrequest limits (50 subrequests on Workers
  Bundled, 1 000 on Workers Unbound).

## Verification

```bash
# Write to Tokyo local DO and read from London — propagation should complete within ~10 s
curl -X POST https://api.example.com/write \
  -H "CF-IPCountry: JP" \
  -d '{"key":"theme","value":"dark"}'

sleep 10

curl https://api.example.com/read?key=theme \
  -H "CF-IPCountry: GB"
# Expected: {"value":"dark", "hlc":"..."}

# Simulate concurrent conflicting writes and verify LWW resolution
```

## Related

- `multi-region-architecture.md`
- `multi-region-write-patterns.md`
- `active-active-vs-active-passive.md`
- `crdt-conflict-free-data-types.md`
- `hybrid-logical-clocks.md`
- `durable-object-alarm-api-scheduled-retry.md`

## Sources

- Cloudflare Durable Objects location hints — https://developers.cloudflare.com/durable-objects/reference/configuration/
- Hybrid Logical Clocks — Kulkarni et al. 2014 — https://cse.buffalo.edu/tech-reports/2014-04.pdf
- CRDT literature — Shapiro et al. "A Comprehensive Study of CRDTs" — https://hal.inria.fr/inria-00555588
