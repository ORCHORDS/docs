# Polyglot Persistence on Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A single data store cannot optimally serve every access pattern in a real-world application.
Relational queries, low-latency key lookups, large binary assets, real-time session state,
and semantic vector search each call for a different engine. On the Cloudflare stack you
have D1, KV, R2, Durable Objects, and Vectorize in the same process — the challenge is
deciding which store owns which data and preventing cross-store consistency problems.

## Context

Polyglot persistence is the practice of using multiple, specialised storage technologies within
one system and routing each data type to the store that fits it best. On Cloudflare Workers
the available primitives and their primary strengths are:

| Store           | Strength                                              | Consistency       |
|-----------------|-------------------------------------------------------|-------------------|
| D1              | Relational queries, foreign keys, ACID per statement  | Strong (regional) |
| KV              | Global low-latency reads, configuration, feature flags| Eventual          |
| R2              | Large objects (audio, video, PDFs, blobs)             | Strong (per-key)  |
| Durable Objects | Single-entity strong consistency, real-time state     | Linearisable      |
| Vectorize       | ANN semantic search over embedding vectors            | Eventually indexed|

The system-of-record for every entity must be exactly one store; other stores hold derived
projections updated asynchronously via Queues.

## Routing Layer — The Storage Gateway

A `StorageGateway` abstracts store selection behind a single interface. Callers never
reference individual bindings directly.

```typescript
// storage-gateway.ts
export interface StorageGateway {
  // Structured data
  query<T>(sql: string, params?: unknown[]): Promise<T[]>;
  // Fast edge lookups
  get(key: string): Promise<string | null>;
  set(key: string, value: string, ttlSeconds?: number): Promise<void>;
  // Large binary blobs
  putBlob(key: string, body: ReadableStream, contentType: string): Promise<void>;
  getBlob(key: string): Promise<Response | null>;
  // Semantic search
  search(vector: number[], topK: number): Promise<VectorizeMatch[]>;
}

export function createGateway(env: Env): StorageGateway {
  return {
    async query<T>(sql: string, params: unknown[] = []) {
      const stmt = env.DB.prepare(sql);
      const result = params.length
        ? await stmt.bind(...params).all<T>()
        : await stmt.all<T>();
      return result.results;
    },
    async get(key) {
      return env.KV.get(key);
    },
    async set(key, value, ttlSeconds) {
      await env.KV.put(key, value, ttlSeconds ? { expirationTtl: ttlSeconds } : undefined);
    },
    async putBlob(key, body, contentType) {
      await env.ASSETS.put(key, body, { httpMetadata: { contentType } });
    },
    async getBlob(key) {
      const obj = await env.ASSETS.get(key);
      if (!obj) return null;
      return new Response(obj.body, {
        headers: { "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream" },
      });
    },
    async search(vector, topK) {
      const result = await env.VECTORIZE.query(vector, { topK });
      return result.matches;
    },
  };
}
```

## Write Path — System-of-Record → Projection

Every mutation goes to the system-of-record first, then enqueues a projection event.
The Queue fan-out updates secondary stores without blocking the primary write.

```typescript
// write-path.ts
export async function createDocument(
  env: Env,
  gw: StorageGateway,
  doc: { id: string; title: string; body: string; embedding: number[] }
): Promise<void> {
  // 1. System-of-record: D1 (ACID insert)
  await gw.query(
    "INSERT INTO documents (id, title, body, created_at) VALUES (?, ?, ?, ?)",
    [doc.id, doc.title, doc.body, Date.now()]
  );

  // 2. Enqueue projections asynchronously
  await env.PROJECTION_QUEUE.send({
    type: "document_created",
    id: doc.id,
    title: doc.title,
    embedding: doc.embedding,
  });
}
```

```typescript
// projection-consumer.ts  — Queue consumer Worker
import type { MessageBatch } from "@cloudflare/workers-types";

export default {
  async queue(batch: MessageBatch<ProjectionEvent>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const ev = msg.body;
      if (ev.type === "document_created") {
        // KV projection for fast title lookup
        await env.KV.put(
          `doc:title:${ev.id}`,
          ev.title,
          { expirationTtl: 86400 }
        );
        // Vectorize projection for semantic search
        await env.VECTORIZE.upsert([
          { id: ev.id, values: ev.embedding, metadata: { title: ev.title } },
        ]);
        msg.ack();
      } else {
        msg.retry();
      }
    }
  },
};
```

## Read Path — Choose the Right Store per Query

```typescript
// read-path.ts
export async function resolveRequest(
  req: Request,
  env: Env,
  gw: StorageGateway
): Promise<Response> {
  const url = new URL(req.url);

  // Fast lookup — KV
  if (url.pathname.startsWith("/doc/title/")) {
    const id = url.pathname.split("/").pop()!;
    const title = await gw.get(`doc:title:${id}`);
    if (title) return Response.json({ id, title, source: "kv" });
    // KV miss: fall through to D1
    const [row] = await gw.query<{ title: string }>(
      "SELECT title FROM documents WHERE id = ?", [id]
    );
    if (!row) return new Response("Not Found", { status: 404 });
    // Back-fill KV
    await gw.set(`doc:title:${id}`, row.title, 86400);
    return Response.json({ id, title: row.title, source: "d1" });
  }

  // Semantic search — Vectorize
  if (url.pathname === "/search") {
    const body = await req.json<{ vector: number[] }>();
    const matches = await gw.search(body.vector, 10);
    return Response.json({ matches });
  }

  // Binary asset — R2
  if (url.pathname.startsWith("/asset/")) {
    const key = url.pathname.slice("/asset/".length);
    const blob = await gw.getBlob(key);
    return blob ?? new Response("Not Found", { status: 404 });
  }

  return new Response("Not Found", { status: 404 });
}
```

## Consistency Boundary Management

Each store has different consistency semantics. Mark data with its authoritative source
so callers can reason about staleness.

```typescript
// consistency.ts
export interface StoreResult<T> {
  data: T;
  source: "d1" | "kv" | "r2" | "do" | "vectorize";
  stalePossible: boolean;
}

export async function strongRead<T>(
  gw: StorageGateway,
  sql: string,
  params: unknown[] = []
): Promise<StoreResult<T[]>> {
  const data = await gw.query<T>(sql, params);
  return { data, source: "d1", stalePossible: false };
}

export async function fastRead(
  gw: StorageGateway,
  key: string
): Promise<StoreResult<string | null>> {
  const data = await gw.get(key);
  return { data, source: "kv", stalePossible: true };
}
```

## Anti-patterns

- Writing the same entity to two stores synchronously inside a single Worker request.
  Use a queue for all secondary projections to avoid partial writes.
- Treating KV as a session store for mutable state — KV is eventually consistent and
  has no compare-and-swap; use Durable Objects for mutable session state.
- Storing large blobs (>25 MB) in D1 or KV. Put them in R2 and store only the key reference.
- Letting consumers bypass the gateway and call store bindings directly; this makes it
  impossible to track which store is authoritative for a given field.
- Embedding Vectorize index updates in the hot write path — upserts are eventually indexed
  and slow; always push to a queue.

## Gotchas

- KV values are globally replicated but writes take up to 60 s to propagate worldwide.
  Never use KV for data that must be read back immediately after write.
- Vectorize `query` returns approximate nearest neighbours; results may include IDs that
  no longer exist in D1 if a delete event has not yet propagated to the index.
- R2 object keys are case-sensitive. Normalise keys to lower-case at the gateway layer
  to prevent phantom misses.
- D1 in Workers has a 10 MB result size limit per query response. Paginate large result
  sets with `LIMIT` / `OFFSET` or cursor-based pagination.
- Each Queue consumer Worker has its own bindings; verify all projection consumers declare
  the same KV, R2, and Vectorize bindings in `wrangler.toml`.

## Verification

1. Insert a document and confirm the D1 row exists before the Queue consumer fires.
2. After the Queue consumer processes the message, assert KV returns the title.
3. Wait for Vectorize indexing (typically < 10 s) and run a semantic query; confirm the
   document appears in the top-10 matches.
4. Delete the document from D1 and send a `document_deleted` projection event; confirm KV
   key is deleted and Vectorize entry is removed.
5. Upload a binary asset to R2 and fetch via the `/asset/` path; confirm `Content-Type` header.

## Related

- `caching-layers-cloudflare-workers-kv-r2.md`
- `d1-vectorize-semantic-search-cqrs-read-model.md`
- `event-carried-state-transfer-workers-kv.md`
- `outbox-pattern-workers-queues-reliable-events.md`
- `write-coalescing-durable-objects-d1.md`

## Sources

- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare Vectorize: https://developers.cloudflare.com/vectorize/
- Cloudflare R2: https://developers.cloudflare.com/r2/
- Martin Fowler — Polyglot Persistence: https://martinfowler.com/bliki/PolyglotPersistence.html
