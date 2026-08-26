# D1 + R2 Blob Offload — Metadata-in-Database Pattern for Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need to store user-uploaded files (images, PDFs, audio) alongside searchable, filterable
metadata — owner, size, MIME type, created-at, tags. Embedding binary blobs in D1 rows is
problematic: D1 rows have a 1 MB hard limit, binary data inflates D1 storage costs, and large
BLOBs slow down row reads unrelated to the file content. R2 provides cheap unlimited object
storage; D1 provides relational queries. The correct architecture is: **blobs live in R2, all
metadata and relationships live in D1**.

## Context

Cloudflare Workers expose both `env.DB` (D1Database) and `env.BUCKET` (R2Bucket) as bindings.
Write and read operations on both bindings happen inside the same Worker without any external
network hop. R2 keys are arbitrary strings — using a UUID generated at upload time as the R2
key decouples the storage key from user-visible file names and prevents enumeration.

Transactional guarantees between D1 and R2 do not exist natively — they are separate systems.
The safe ordering is:

1. Write to R2 first (idempotent by key).
2. Insert the metadata row in D1.
3. On failure at step 2, orphan cleanup runs asynchronously (e.g., a scheduled Worker or a
   dead-letter queue).

Deletion is the reverse: soft-delete the D1 row first, then delete the R2 object, then hard-delete.

## Wrangler Bindings

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "myapp"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[r2_buckets]]
binding = "BUCKET"
bucket_name = "myapp-uploads"
```

## D1 Schema

```sql
-- migrations/0002_file_metadata.sql
CREATE TABLE file_metadata (
  id           TEXT PRIMARY KEY,          -- UUID v4, same as R2 key
  owner_id     TEXT NOT NULL,
  filename     TEXT NOT NULL,
  mime_type    TEXT NOT NULL,
  size_bytes   INTEGER NOT NULL,
  r2_key       TEXT NOT NULL UNIQUE,      -- redundant with id but explicit
  uploaded_at  TEXT NOT NULL,
  deleted_at   TEXT,                      -- soft-delete sentinel
  tags         TEXT NOT NULL DEFAULT '[]' -- JSON array
) STRICT;

CREATE INDEX idx_file_metadata_owner ON file_metadata (owner_id, uploaded_at DESC)
  WHERE deleted_at IS NULL;
```

## Upload Handler

```typescript
// src/handlers/upload.ts
import type { D1Database, R2Bucket } from "@cloudflare/workers-types";
import { randomUUID } from "node:crypto"; // available in Workers runtime

interface Env {
  DB: D1Database;
  BUCKET: R2Bucket;
}

interface FileMetadataRow {
  id: string;
  owner_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  r2_key: string;
  uploaded_at: string;
  tags: string;
}

export async function handleUpload(
  request: Request,
  env: Env,
  ownerId: string
): Promise<Response> {
  const formData = await request.formData();
  const file = formData.get("file");

  if (!(file instanceof File)) {
    return new Response("Missing file field", { status: 400 });
  }

  if (file.size > 100 * 1024 * 1024) {
    return new Response("File exceeds 100 MB limit", { status: 413 });
  }

  const fileId = randomUUID();
  const r2Key = `uploads/${ownerId}/${fileId}`;
  const now = new Date().toISOString();

  // Step 1: Write to R2 first — idempotent, safe to retry
  await env.BUCKET.put(r2Key, await file.arrayBuffer(), {
    httpMetadata: { contentType: file.type },
    customMetadata: { ownerId, originalName: file.name },
  });

  // Step 2: Record metadata in D1
  try {
    const row = await env.DB.prepare(
      `INSERT INTO file_metadata
         (id, owner_id, filename, mime_type, size_bytes, r2_key, uploaded_at, tags)
       VALUES (?, ?, ?, ?, ?, ?, ?, '[]')
       RETURNING *`
    )
      .bind(fileId, ownerId, file.name, file.type, file.size, r2Key, now)
      .first<FileMetadataRow>();

    return Response.json(row, { status: 201 });
  } catch (err) {
    // Best-effort rollback: delete the R2 object to avoid orphans
    await env.BUCKET.delete(r2Key).catch(() => {});
    throw err;
  }
}
```

## Download / Signed URL Handler

```typescript
// src/handlers/download.ts
import type { D1Database, R2Bucket } from "@cloudflare/workers-types";

interface FileMetadataRow {
  id: string;
  owner_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  r2_key: string;
}

export async function handleDownload(
  fileId: string,
  requestingOwnerId: string,
  env: { DB: D1Database; BUCKET: R2Bucket }
): Promise<Response> {
  // Authorise via D1 — never trust a client-supplied R2 key directly
  const meta = await env.DB.prepare(
    `SELECT * FROM file_metadata
     WHERE id = ? AND owner_id = ? AND deleted_at IS NULL`
  )
    .bind(fileId, requestingOwnerId)
    .first<FileMetadataRow>();

  if (!meta) return new Response("Not found", { status: 404 });

  const object = await env.BUCKET.get(meta.r2_key);
  if (!object) return new Response("Object missing in R2", { status: 502 });

  return new Response(object.body, {
    headers: {
      "Content-Type": meta.mime_type,
      "Content-Disposition": `attachment; filename="${meta.filename}"`,
      "Content-Length": String(meta.size_bytes),
      "Cache-Control": "private, max-age=3600",
    },
  });
}
```

## Soft-Delete and Async R2 Cleanup

```typescript
// src/handlers/delete.ts
import type { D1Database, R2Bucket } from "@cloudflare/workers-types";

export async function handleDelete(
  fileId: string,
  ownerId: string,
  env: { DB: D1Database; BUCKET: R2Bucket }
): Promise<Response> {
  // Step 1: Soft-delete in D1 — makes the file invisible to queries immediately
  const result = await env.DB.prepare(
    `UPDATE file_metadata
     SET deleted_at = ?
     WHERE id = ? AND owner_id = ? AND deleted_at IS NULL`
  )
    .bind(new Date().toISOString(), fileId, ownerId)
    .run();

  if (result.meta.changes === 0) {
    return new Response("Not found", { status: 404 });
  }

  // Step 2: Delete R2 object (best-effort in same request; move to queue if large scale)
  const meta = await env.DB.prepare(
    "SELECT r2_key FROM file_metadata WHERE id = ?"
  )
    .bind(fileId)
    .first<{ r2_key: string }>();

  if (meta) await env.BUCKET.delete(meta.r2_key).catch(() => {});

  return new Response(null, { status: 204 });
}
```

## Orphan Sweep (Scheduled Worker)

```typescript
// src/scheduled/orphan-sweep.ts
import type { D1Database, R2Bucket } from "@cloudflare/workers-types";

// Run via Cron Trigger: "0 3 * * *" (daily at 03:00 UTC)
export async function sweepOrphans(env: { DB: D1Database; BUCKET: R2Bucket }) {
  // Files soft-deleted more than 7 days ago
  const cutoff = new Date(Date.now() - 7 * 86_400_000).toISOString();

  const { results } = await env.DB.prepare(
    `SELECT id, r2_key FROM file_metadata
     WHERE deleted_at IS NOT NULL AND deleted_at < ?
     LIMIT 100`
  )
    .bind(cutoff)
    .all<{ id: string; r2_key: string }>();

  if (results.length === 0) return;

  // Delete from R2 first, then hard-delete D1 rows
  await Promise.all(results.map((r) => env.BUCKET.delete(r.r2_key)));

  const ids = results.map(() => "?").join(",");
  await env.DB.prepare(
    `DELETE FROM file_metadata WHERE id IN (${ids})`
  )
    .bind(...results.map((r) => r.id))
    .run();
}
```

## Anti-patterns

- **Storing R2 keys as user-supplied filenames** — predictable keys allow enumeration; always
  use a UUID as the key and store the user's filename in D1 only.
- **Writing D1 first, then R2** — if the R2 write fails after D1 insert, you have a metadata row
  pointing to a non-existent object. Write R2 first.
- **Reading R2 object size from the object at download time** — this requires an additional
  `HEAD` request; cache `size_bytes` in D1 instead.
- **Storing MIME type from the client directly without validation** — clients can send any
  `Content-Type`; validate against an allowlist before inserting into D1.
- **Hard-deleting D1 rows synchronously with R2 delete** — if R2 delete fails, re-querying D1
  gives no way to retry. Soft-delete first, hard-delete after confirmed R2 removal.

## Gotchas

- **R2 `put` is not transactional** — concurrent uploads with the same key last-write-wins;
  use UUIDs to avoid collisions entirely.
- **R2 `get` returns `null` if the key doesn't exist** — always check for null before streaming
  the body, then return a 502 (not 404) because the D1 metadata said the object should exist.
- **Workers CPU limit** — streaming a large R2 object through `object.body` does not count
  toward CPU time, but reading it into an `ArrayBuffer` does; use `object.body` (a `ReadableStream`)
  directly in the `Response` constructor.
- **D1 query during upload adds latency** — the R2 write is the slow step; fire the D1 insert
  immediately after without awaiting the entire response delivery.

## Verification

```bash
# Confirm metadata row and R2 key match after upload
wrangler d1 execute myapp --command \
  "SELECT id, r2_key, size_bytes FROM file_metadata ORDER BY uploaded_at DESC LIMIT 5;"

wrangler r2 object list myapp-uploads --prefix "uploads/" | head -20
```

## Related

- `d1-soft-delete-workers-middleware.md`
- `d1-dead-letter-queue-retry-workers.md`
- `d1-text-compression-r2-offload.md`
- `d1-row-level-security-tenant-id.md`

## Sources

- Cloudflare R2 Workers API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- R2 object size limits: https://developers.cloudflare.com/r2/objects/
- Workers Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
