# D1 BLOB Binary Data Storage Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to store small binary payloads — encrypted tokens, cryptographic signatures,
compact serialised structs, or pre-rendered thumbnails — directly inside a D1 row
instead of uploading them to R2 and keeping only a URL.  You want atomic
read-modify-write on the binary field within a single database transaction and want
to avoid the extra latency of an R2 round-trip for every read.

---

## Context

SQLite (and by extension Cloudflare D1) has a native `BLOB` storage class.  Any
column declared as `BLOB` (or as `NONE` in typeless form) stores arbitrary byte
strings with zero transcoding.  D1's HTTP API serialises BLOB values as Base64
inside JSON, and the Workers binding surfaces them as `ArrayBuffer`.  The practical
size ceiling per cell is a few megabytes before you hit D1's per-request payload
limit; anything larger belongs in R2.  Under STRICT mode the column type must be
`BLOB` — the database rejects text/integer values, which prevents accidental
double-encoding.

---

## Schema design

```sql
-- migrations/0012_binary_storage.sql
CREATE TABLE IF NOT EXISTS asset_blobs (
  id          TEXT    PRIMARY KEY,           -- UUID v7
  mime_type   TEXT    NOT NULL,
  byte_length INTEGER NOT NULL,
  data        BLOB    NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
) STRICT;

CREATE INDEX idx_asset_blobs_created ON asset_blobs (created_at);
```

Keep a `byte_length` shadow column so callers can decide whether to fetch the BLOB
without actually reading it.

---

## Writing a BLOB from a Worker

```typescript
// src/lib/blob-store.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface BlobRecord {
  id: string;
  mime_type: string;
  byte_length: number;
  data: ArrayBuffer;
  created_at: number;
  updated_at: number;
}

/**
 * Persist an ArrayBuffer as a BLOB cell in D1.
 * The Workers binding accepts ArrayBuffer values directly in the
 * parameterised query array — no manual Base64 needed.
 */
export async function putBlob(
  db: D1Database,
  id: string,
  mimeType: string,
  data: ArrayBuffer,
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO asset_blobs (id, mime_type, byte_length, data)
       VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT (id) DO UPDATE SET
         mime_type   = excluded.mime_type,
         byte_length = excluded.byte_length,
         data        = excluded.data,
         updated_at  = unixepoch()`,
    )
    .bind(id, mimeType, data.byteLength, data)
    .run();
}

/** Fetch just the metadata without pulling the binary payload. */
export async function getBlobMeta(
  db: D1Database,
  id: string,
): Promise<Omit<BlobRecord, 'data'> | null> {
  return db
    .prepare(
      `SELECT id, mime_type, byte_length, created_at, updated_at
       FROM asset_blobs WHERE id = ?1`,
    )
    .bind(id)
    .first<Omit<BlobRecord, 'data'>>();
}

/** Fetch the full record including the binary payload. */
export async function getBlob(
  db: D1Database,
  id: string,
): Promise<BlobRecord | null> {
  return db
    .prepare(`SELECT * FROM asset_blobs WHERE id = ?1`)
    .bind(id)
    .first<BlobRecord>();
}
```

---

## Worker handler — store and serve blobs via HTTP

```typescript
// src/handlers/blob-handler.ts
import { putBlob, getBlob, getBlobMeta } from '../lib/blob-store';

export async function handleBlobPut(
  request: Request,
  env: Env,
): Promise<Response> {
  const id = new URL(request.url).pathname.split('/').at(-1) ?? '';
  if (!id) return new Response('Missing id', { status: 400 });

  const contentType = request.headers.get('Content-Type') ?? 'application/octet-stream';
  const body = await request.arrayBuffer();

  if (body.byteLength > 4 * 1024 * 1024) {
    return new Response('Payload too large; use R2 for blobs > 4 MB', { status: 413 });
  }

  await putBlob(env.DB, id, contentType, body);
  return new Response(null, { status: 204 });
}

export async function handleBlobGet(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const id = url.pathname.split('/').at(-1) ?? '';
  const metaOnly = url.searchParams.has('meta');

  if (metaOnly) {
    const meta = await getBlobMeta(env.DB, id);
    if (!meta) return new Response('Not found', { status: 404 });
    return Response.json(meta);
  }

  const record = await getBlob(env.DB, id);
  if (!record) return new Response('Not found', { status: 404 });

  return new Response(record.data as ArrayBuffer, {
    headers: {
      'Content-Type': record.mime_type,
      'Content-Length': String(record.byte_length),
      'Cache-Control': 'private, max-age=3600',
    },
  });
}
```

---

## Transactional update of a BLOB field

```typescript
// Atomically replace an encrypted token and invalidate a cache entry in one tx.
export async function rotateEncryptedToken(
  db: D1Database,
  id: string,
  newTokenBytes: ArrayBuffer,
): Promise<void> {
  await db.batch([
    db
      .prepare(
        `UPDATE asset_blobs
         SET data = ?1, byte_length = ?2, updated_at = unixepoch()
         WHERE id = ?3`,
      )
      .bind(newTokenBytes, newTokenBytes.byteLength, id),

    db
      .prepare(`DELETE FROM token_cache WHERE asset_id = ?1`)
      .bind(id),
  ]);
}
```

---

## Encoding round-trip for external consumers

D1's REST API returns BLOB columns as Base64 strings.  The Workers binding converts
them to `ArrayBuffer` transparently, but if you hit D1 via `fetch` (e.g. from a
non-Worker runtime) you must decode manually:

```typescript
// Decoding Base64 from D1 REST response in a non-Worker context
function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}
```

---

## Anti-patterns

- **Storing large files in BLOB** — D1 is not a file store.  Blobs above ~1 MB add
  measurable read latency and push your row close to the per-statement payload
  ceiling.  Use R2 for anything user-generated or larger than a few kilobytes.

- **Double-encoding** — Running `Buffer.from(data).toString('base64')` before
  binding encodes the value as TEXT, not BLOB.  The stored type changes, STRICT mode
  rejects the insert, and reads silently return a string instead of ArrayBuffer.

- **Selecting BLOB columns in aggregate queries** — `SELECT *` on a large table that
  includes a BLOB column transfers every byte for every row even if you only need
  counts.  Always project specific columns.

- **Storing BLOBs without a size guard** — Workers silently truncate oversized
  bindings in some error paths.  Always check `byteLength` before binding and return
  a 413 early.

---

## Gotchas

- D1 STRICT tables require the column type to be one of `INT`, `INTEGER`, `REAL`,
  `TEXT`, `BLOB`, `ANY`.  Using `BYTEA`, `BINARY`, or `VARBINARY` causes a schema
  parse error at migration time.

- `result.first<T>()` typed as `T` casts the raw object but does not convert BLOB
  columns.  The `data` field arrives as `ArrayBuffer` from the Workers runtime; if
  your TypeScript interface types it as `string` TypeScript compiles but the runtime
  value is wrong.

- SQLite BLOB comparisons use byte-order (`<`, `>`) not UTF-8 collation.  Sorting a
  BLOB column sorts lexicographically by raw bytes, which is rarely what you want.

- The `||` concatenation operator promotes BLOB operands to TEXT, corrupting binary
  data.  Use `zeroblob()` and `substr()` for binary manipulation.

---

## Verification

```typescript
// Integration test with Miniflare / Vitest
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { putBlob, getBlob } from '../src/lib/blob-store';

describe('BLOB round-trip', () => {
  beforeAll(async () => {
    await env.DB.exec(
      `CREATE TABLE IF NOT EXISTS asset_blobs (
         id TEXT PRIMARY KEY, mime_type TEXT NOT NULL,
         byte_length INTEGER NOT NULL, data BLOB NOT NULL,
         created_at INTEGER NOT NULL DEFAULT (unixepoch()),
         updated_at INTEGER NOT NULL DEFAULT (unixepoch())
       ) STRICT`,
    );
  });

  it('stores and retrieves binary data without corruption', async () => {
    const original = new Uint8Array([0xff, 0x00, 0xab, 0xcd, 0x12]);
    await putBlob(env.DB, 'test-1', 'application/octet-stream', original.buffer);
    const record = await getBlob(env.DB, 'test-1');
    expect(record).not.toBeNull();
    const retrieved = new Uint8Array(record!.data as ArrayBuffer);
    expect(retrieved).toEqual(original);
  });

  it('reports correct byte_length', async () => {
    const data = new Uint8Array(512).fill(0xaa);
    await putBlob(env.DB, 'test-2', 'image/png', data.buffer);
    const record = await getBlob(env.DB, 'test-2');
    expect(record?.byte_length).toBe(512);
  });
});
```

Run: `npx vitest run src/__tests__/blob-store.test.ts`

---

## Related

- `d1-r2-blob-offload-metadata-pattern-workers.md` — when blobs exceed D1's practical
  size ceiling, offload the payload to R2 and keep only a URL + metadata in D1.
- `d1-strict-tables-type-enforcement-workers.md` — STRICT mode prevents TEXT/INTEGER
  values from landing in a BLOB column.
- `d1-json-column-patterns.md` — storing structured data as JSON TEXT vs. BLOB.
- `d1-tenant-data-encryption-workers.md` — encrypting BLOB fields with the Web Crypto
  API before persistence.

---

## Sources

- SQLite documentation — Storage Classes and Datatypes: https://www.sqlite.org/datatype3.html
- Cloudflare D1 documentation — Workers binding: https://developers.cloudflare.com/d1/worker-api/
- SQLite BLOB literals and functions: https://www.sqlite.org/lang_expr.html
- Cloudflare D1 STRICT tables: https://developers.cloudflare.com/d1/reference/database-commands/
