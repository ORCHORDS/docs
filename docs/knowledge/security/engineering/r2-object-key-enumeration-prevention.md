# R2 Object Key Enumeration Prevention and Secure Access Patterns

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Cloudflare R2 bucket stores per-user files using predictable key patterns like `users/{userId}/documents/{docId}.pdf`. An authenticated user who discovers the key structure can attempt to access other users' objects by guessing or incrementing IDs — an Insecure Direct Object Reference (IDOR) vulnerability at the storage layer. If the bucket is also publicly exposed (custom domain or `r2.dev` subdomain), object listing and predictable key names allow unauthenticated enumeration of all stored content.

Even with presigned URLs, the `GET /list-objects` style API endpoint or any Worker that reflects object keys back to the client can leak the namespace structure. The goal is to ensure that object keys are never predictable from user-controlled inputs and that the only way to reach an object is through a Worker that enforces ownership checks.

## Context

Cloudflare R2 is an S3-compatible object store bound to Workers via `env.MY_BUCKET` (an `R2Bucket` binding). Unlike S3, R2 does not charge for egress, but it shares S3's flat key namespace model: any caller with a bucket credential can list all keys unless explicitly restricted.

Workers are the access control layer for R2 — you never expose R2 credentials directly to clients. But Workers that pass user input directly into `bucket.get(key)` calls without ownership validation are vulnerable to IDOR. The defenses are: (1) opaque, unguessable object keys; (2) Worker-enforced ownership lookup via D1 before serving any object; (3) no object listing API exposed to clients.

## Opaque Object Keys Using Cryptographic Randomness

Replace predictable key patterns with random, unguessable identifiers. Map the random key to the user's ownership record in D1.

```typescript
// src/r2-upload.ts

interface Env {
  STORAGE: R2Bucket;
  DB: D1Database;
}

interface UploadRecord {
  objectKey: string;
  userId: string;
  originalName: string;
  contentType: string;
  sizeBytes: number;
  uploadedAt: number;
}

/**
 * Generate a cryptographically random R2 object key.
 * Format: {prefix}/{32-hex-random-bytes}
 * The prefix is a fixed namespace hint (e.g., "doc", "img") NOT the user ID.
 */
function generateObjectKey(prefix: string): string {
  const random = new Uint8Array(32);
  crypto.getRandomValues(random);
  const hex = Array.from(random).map(b => b.toString(16).padStart(2, "0")).join("");
  return `${prefix}/${hex}`;
}

export async function handleUpload(
  request: Request,
  env: Env,
  userId: string
): Promise<Response> {
  const contentType = request.headers.get("Content-Type") ?? "application/octet-stream";
  const originalName = request.headers.get("X-File-Name")?.slice(0, 255) ?? "untitled";

  // Validate content type against allowlist
  const allowedTypes = new Set([
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
  ]);
  if (!allowedTypes.has(contentType)) {
    return new Response("Content type not allowed", { status: 415 });
  }

  // Size limit check via Content-Length header (not authoritative, verify on R2 side)
  const contentLength = parseInt(request.headers.get("Content-Length") ?? "0", 10);
  const maxSize = 50 * 1024 * 1024; // 50 MB
  if (contentLength > maxSize) {
    return new Response("File too large", { status: 413 });
  }

  // Prefix by content type category, never by user ID
  const prefix = contentType.startsWith("image/") ? "img" : "doc";
  const objectKey = generateObjectKey(prefix);

  // Upload to R2 with no user-identifying metadata in the key
  const r2Object = await env.STORAGE.put(objectKey, request.body, {
    httpMetadata: { contentType },
    customMetadata: {
      uploadedBy: userId,   // stored in metadata, not the key
      originalName,
    },
  });

  if (!r2Object) {
    return new Response("Upload failed", { status: 500 });
  }

  // Record ownership in D1 — this is the authoritative access control record
  const fileId = crypto.randomUUID(); // client-facing ID, also opaque
  await env.DB.prepare(`
    INSERT INTO user_files (file_id, user_id, object_key, original_name, content_type, size_bytes, uploaded_at)
    VALUES (?, ?, ?, ?, ?, ?, unixepoch())
  `).bind(
    fileId,
    userId,
    objectKey,
    originalName,
    contentType,
    r2Object.size,
  ).run();

  return Response.json({ fileId, originalName, sizeBytes: r2Object.size });
}
```

## Worker-Enforced Ownership Validation Before Object Retrieval

Every `R2Bucket.get()` call must be preceded by a D1 ownership lookup. Never trust the client-supplied file ID to map directly to an object key.

```typescript
// src/r2-download.ts

interface Env {
  STORAGE: R2Bucket;
  DB: D1Database;
}

interface FileRecord {
  object_key: string;
  content_type: string;
  original_name: string;
  size_bytes: number;
}

export async function handleDownload(
  request: Request,
  env: Env,
  userId: string,
  fileId: string
): Promise<Response> {
  // Validate fileId is a UUID to prevent injection into D1 query
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(fileId)) {
    return new Response("Not Found", { status: 404 });
  }

  // D1 ownership lookup — the object_key is never exposed to the client
  const record = await env.DB.prepare(`
    SELECT object_key, content_type, original_name, size_bytes
    FROM user_files
    WHERE file_id = ? AND user_id = ? AND deleted_at IS NULL
  `).bind(fileId, userId).first<FileRecord>();

  if (!record) {
    // Return 404 not 403 to avoid confirming that the file exists but belongs to another user
    return new Response("Not Found", { status: 404 });
  }

  // Range request support for large files
  const rangeHeader = request.headers.get("Range");

  const r2Options: R2GetOptions = {};
  if (rangeHeader) {
    const match = rangeHeader.match(/bytes=(\d+)-(\d*)/);
    if (match) {
      const offset = parseInt(match[1], 10);
      const length = match[2] ? parseInt(match[2], 10) - offset + 1 : undefined;
      r2Options.range = { offset, length };
    }
  }

  const object = await env.STORAGE.get(record.object_key, r2Options);

  if (!object) {
    // Object key exists in D1 but not in R2 — data inconsistency
    console.error(`R2 object not found for file_id=${fileId}, key=${record.object_key}`);
    return new Response("Not Found", { status: 404 });
  }

  const headers = new Headers({
    "Content-Type": record.content_type,
    "Content-Disposition": `attachment; filename="${sanitizeFilename(record.original_name)}"`,
    "Cache-Control": "private, max-age=300",
    "X-Content-Type-Options": "nosniff",
  });

  if (object.size) {
    headers.set("Content-Length", object.size.toString());
  }

  return new Response(object.body, {
    status: rangeHeader ? 206 : 200,
    headers,
  });
}

function sanitizeFilename(name: string): string {
  // Strip characters that could escape Content-Disposition header
  return name.replace(/["\\\r\n]/g, "").slice(0, 200);
}
```

## Preventing Object Listing API Exposure

Never expose a listing endpoint that returns object keys. If clients need to browse their files, return only the opaque `fileId` values from D1.

```typescript
// src/r2-list.ts

interface Env {
  DB: D1Database;
  // Note: no STORAGE binding here — listing goes through D1 only
}

interface FileListItem {
  file_id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  uploaded_at: number;
}

export async function handleList(
  request: Request,
  env: Env,
  userId: string
): Promise<Response> {
  const url = new URL(request.url);
  const cursor = url.searchParams.get("cursor");
  const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "20", 10), 100);

  // Cursor-based pagination to avoid offset scans on large datasets
  let query: string;
  let bindings: (string | number)[];

  if (cursor) {
    // Validate cursor is a valid integer (uploaded_at timestamp for cursor pagination)
    const cursorTs = parseInt(cursor, 10);
    if (isNaN(cursorTs)) {
      return new Response("Invalid cursor", { status: 400 });
    }
    query = `
      SELECT file_id, original_name, content_type, size_bytes, uploaded_at
      FROM user_files
      WHERE user_id = ? AND deleted_at IS NULL AND uploaded_at < ?
      ORDER BY uploaded_at DESC
      LIMIT ?
    `;
    bindings = [userId, cursorTs, limit + 1];
  } else {
    query = `
      SELECT file_id, original_name, content_type, size_bytes, uploaded_at
      FROM user_files
      WHERE user_id = ? AND deleted_at IS NULL
      ORDER BY uploaded_at DESC
      LIMIT ?
    `;
    bindings = [userId, limit + 1];
  }

  const stmt = env.DB.prepare(query);
  const { results } = await stmt.bind(...bindings).all<FileListItem>();

  const hasMore = results.length > limit;
  const items = hasMore ? results.slice(0, limit) : results;
  const nextCursor = hasMore ? items[items.length - 1].uploaded_at.toString() : null;

  return Response.json({
    files: items,  // Contains only file_id, never object_key
    nextCursor,
  });
}
```

## D1 Schema for Ownership Tracking

```sql
CREATE TABLE IF NOT EXISTS user_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_id TEXT NOT NULL UNIQUE,        -- opaque UUID given to client
  user_id TEXT NOT NULL,               -- owner
  object_key TEXT NOT NULL UNIQUE,     -- opaque R2 key, never exposed to client
  original_name TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  uploaded_at INTEGER NOT NULL,
  deleted_at INTEGER,                  -- soft delete; R2 object cleared async
  share_token TEXT                     -- nullable: opaque token for shared links
);

CREATE INDEX idx_user_files_user ON user_files(user_id, deleted_at, uploaded_at DESC);
CREATE INDEX idx_user_files_share ON user_files(share_token) WHERE share_token IS NOT NULL;

-- Audit log for access events
CREATE TABLE IF NOT EXISTS file_access_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  action TEXT NOT NULL,  -- upload | download | delete | share
  ip TEXT,
  ts INTEGER NOT NULL
);
```

## Anti-patterns

- Using `userId` or any user-controlled value as part of the R2 object key — enables IDOR by traversal
- Exposing `R2Bucket.list()` output to clients — leaks the full key namespace including other users' keys
- Using sequential numeric IDs as `fileId` — easy to enumerate; use UUID v4 or random hex
- Setting the R2 bucket to public (`r2.dev` subdomain) while using a Worker for access control — the public URL bypasses the Worker entirely
- Reflecting the object key in download URLs or response headers — client learns the key structure
- Relying on obscurity of the key format as the access control — defense must be enforced server-side

## Gotchas

- `env.STORAGE.get(key)` returns `null` if the object does not exist (not an error); always check before reading `.body`
- R2 object metadata (`customMetadata`) is returned with every `head()` or `get()` call — avoid storing sensitive data there that could be read if the bucket were publicly exposed
- Soft-deleting a `user_files` row without also deleting from R2 leaves orphaned objects that still exist in the bucket — run a scheduled cleanup Worker that calls `env.STORAGE.delete(record.object_key)` for rows with non-null `deleted_at`
- R2 does not support object ACLs at the key level — all access control must be implemented in the Worker
- `R2Bucket.list()` with a prefix does not provide security isolation — another Worker with the same binding can list all keys with any prefix

## Verification

```bash
# 1. Upload a file and note the returned fileId
FILE_ID=$(curl -s -X POST https://api.example.com/files \
  -H "Authorization: Bearer <token_user_a>" \
  -H "Content-Type: application/pdf" \
  -H "X-File-Name: test.pdf" \
  --data-binary @test.pdf | jq -r '.fileId')

# 2. Try to access the file as user B using user A's fileId — must get 404
curl -s -o /dev/null -w "%{http_code}" \
  https://api.example.com/files/${FILE_ID} \
  -H "Authorization: Bearer <token_user_b>"
# Expect: 404

# 3. Confirm the R2 object key is not present in any response header
curl -v https://api.example.com/files/${FILE_ID} \
  -H "Authorization: Bearer <token_user_a>" 2>&1 | grep -i "doc\|img\|object"
# Expect: no lines containing the internal key prefix

# 4. Confirm the list endpoint returns only fileIds, no object keys
curl -s https://api.example.com/files \
  -H "Authorization: Bearer <token_user_a>" | jq '.files[0] | keys'
# Expect: ["content_type", "file_id", "original_name", "size_bytes", "uploaded_at"]
# Must NOT contain: "object_key"
```

## Related

- `r2-presigned-url-security.md` — time-limited presigned URL security model
- `r2-bucket-public-exposure-audit.md` — auditing and remediating public bucket exposure
- `idor-insecure-direct-object-reference.md` — IDOR vulnerability class overview
- `d1-row-level-security-tenant-isolation.md` — row-level security patterns for D1

## Sources

- Cloudflare R2 Workers Bindings documentation — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- OWASP Insecure Direct Object Reference Prevention Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
- OWASP API Security Top 10 — API3:2023 Broken Object Property Level Authorization — https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
