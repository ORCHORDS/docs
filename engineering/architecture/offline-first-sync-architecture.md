# Offline-First Sync Architecture

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Users lose unsaved work when the network drops mid-edit. On
reconnect, concurrent edits from two devices overwrite each
other silently. The app shows stale data for several seconds
after a mutation because it waits for a server round-trip
before re-rendering.

## Context

Offline-first (local-first) architecture stores the
authoritative working copy of data on the client and syncs
to the server asynchronously. The server (D1 on Cloudflare)
is the durable, conflict-resolving source of truth, but the
client never blocks on it for reads or writes. This document
covers data model design, conflict resolution, sync protocol
selection, and integration with Cloudflare D1.

## Local-First Data Model

Every mutable entity carries a client-generated UUID, a
logical clock value (lamport timestamp or vector clock), and
a `synced_at` nullable timestamp.

```typescript
interface LocalPost {
  id: string;            // UUID, client-generated
  tenant_id: string;
  content: string;
  updated_at: number;    // Lamport clock (client)
  server_seq: number | null; // null = unsynced
  deleted: boolean;      // soft-delete for sync
}
```

The local store (IndexedDB via a wrapper, or SQLite via
WASM) must be queryable without network access. All UI reads
go to the local store; mutations are written locally first
and queued for sync.

## CRDT vs Last-Write-Wins

| Strategy        | Guarantees          | Cost   | Best for          |
|-----------------|---------------------|--------|-------------------|
| Last-write-wins | Simple, lossy       | Low    | Non-collaborative |
| LWW + tombstone | Deletes propagate   | Low    | Lists, presence   |
| CRDT (op-based) | Merge without loss  | High   | Collaborative doc |
| CRDT (state)    | Convergent replicas | Medium | Counters, sets    |

For most document-editing use cases on this platform,
last-write-wins on the field level (each field has its own
timestamp) is sufficient and far simpler to implement than
a full CRDT. Use an op-based CRDT (Yjs, Automerge) only
when multiple users edit the same document concurrently and
character-level merge is required.

## Optimistic UI Patterns

Apply mutations to the local store synchronously so the UI
reflects the change instantly. If the server later rejects
the mutation, roll back and notify the user.

```typescript
async function updatePost(
  id: string,
  content: string,
): Promise<void> {
  // 1. Write locally and re-render immediately
  await localDb.posts.update(id, {
    content,
    updated_at: nextLamport(),
    server_seq: null,
  });
  ui.rerender();

  // 2. Enqueue sync (non-blocking)
  syncQueue.enqueue({ type: "UPDATE_POST", id, content });
}
```

Track pending mutations in a sync queue persisted to
IndexedDB so they survive page refreshes.

## Sync Protocol Design

| Protocol | Bandwidth | Complexity | Use when                   |
|----------|-----------|------------|----------------------------|
| Pull     | Higher    | Low        | Small datasets, infrequent |
| Push     | Lower     | Medium     | Server-initiated changes   |
| Hybrid   | Optimal   | High       | Large datasets, real-time  |

Recommended hybrid protocol:

1. **Client sends** a `POST /sync` with a batch of local
   mutations and the client's last-known `server_seq`.
2. **Server applies** mutations in order, resolves conflicts
   using LWW per field, returns new mutations the client
   missed (delta since `server_seq`).
3. **Client merges** the delta into the local store and
   advances `server_seq`.

```typescript
// POST /sync request body
interface SyncRequest {
  tenant_id: string;
  client_seq: number;
  mutations: Mutation[];
}

// Server response
interface SyncResponse {
  server_seq: number;
  delta: ServerMutation[];
  rejected: RejectedMutation[];
}
```

## Conflict Resolution with D1 as Authority

The server resolves conflicts using the `updated_at` Lamport
clock. The mutation with the highest clock value wins per
field. The server's resolved state is returned as the
canonical delta.

```sql
-- D1: apply LWW conflict resolution on upsert
INSERT INTO posts (id, tenant_id, content, updated_at)
  VALUES (?, ?, ?, ?)
  ON CONFLICT(id) DO UPDATE SET
    content    = CASE WHEN excluded.updated_at
                        > posts.updated_at
                      THEN excluded.content
                      ELSE posts.content END,
    updated_at = MAX(excluded.updated_at, posts.updated_at);
```

This single-statement upsert is atomic in D1 and avoids a
read-then-write race.

## Anti-patterns

- Using wall-clock time (`Date.now()`) as the ordering
  signal; clocks skew across devices and the conflict
  resolution produces non-deterministic results.
- Syncing the full local store on every reconnect instead
  of sending only the delta since last `server_seq`; this
  produces unbounded payload sizes.
- Storing binary BLOBs (images, files) in the sync delta;
  use presigned R2 URLs and sync only the URL reference.
- Blocking the UI on sync completion before re-rendering;
  violates the optimistic-first contract and makes offline
  mode indistinguishable from no-offline mode.

## Gotchas

- D1's `ON CONFLICT ... DO UPDATE` requires SQLite 3.24+;
  confirm the D1 runtime version before relying on it.
- Lamport clocks require a monotonically increasing counter
  per client device; storing it in localStorage is lost on
  clear. Persist it in IndexedDB alongside the local store.
- Deleted records must use soft-delete (a `deleted` flag)
  and sync the tombstone; hard-deletes cannot propagate to
  clients that were offline when the delete occurred.
- If the client's `server_seq` is too old (e.g. client was
  offline for weeks), the server may have compacted history;
  handle this with a full re-sync fallback code path.

## Verification

- Simulate a network partition in tests using a Service
  Worker that intercepts fetch; assert mutations applied
  offline appear in the local store and sync on reconnect.
- Assert that two clients editing the same field offline
  converge to the same value after both sync to the server.
- Verify the D1 upsert produces the expected winner when
  given two conflicting mutations with different clocks.

## Related

- architecture/crdt-conflict-free-data-types.md
- architecture/eventual-consistency-ux-design.md
- architecture/event-sourcing-pattern.md
- architecture/consistency-patterns.md
- architecture/hybrid-logical-clocks.md

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/d1/
- https://www.inkandswitch.com/local-first/
- https://developers.cloudflare.com/durable-objects/\
best-practices/websockets/
- https://www.sqlite.org/lang_upsert.html
