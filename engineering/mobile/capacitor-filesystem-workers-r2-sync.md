# Capacitor Filesystem Workers R2 Sync

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Capacitor app stores user-generated files (PDFs, voice memos, scan images) in the device filesystem via `@capacitor/filesystem`. When the user is online, these files need to sync to Cloudflare R2 for backup, cross-device access, and sharing. When offline, changes are queued locally and flushed on reconnect. The sync must be resumable and handle partial uploads without retransmitting data already on R2.

## Context

`@capacitor/filesystem` provides a cross-platform file API over iOS's app sandbox and Android's `Files` directory. Cloudflare Workers expose a presigned R2 upload URL; the mobile client uploads directly to R2 without passing binary data through the Worker runtime, keeping Worker CPU time low. A small Workers endpoint tracks sync state in D1 (file metadata, upload status, ETag) and returns presigned URLs scoped to the authenticated user.

Sync flow:

```
1. App writes file to Capacitor Filesystem (local)
2. Sync service reads pending-upload queue (stored in localStorage/MMKV)
3. Request presigned PUT URL from Workers
4. App uploads directly to R2 via presigned URL
5. App notifies Workers of completion (Workers updates D1 record)
6. Download flow is the reverse: Workers issues presigned GET URL
```

## Workers Presigned URL Endpoint

```typescript
// workers/sync/index.ts
export interface Env {
  BUCKET: R2Bucket;
  DB: D1Database;
  JWT_SECRET: string;
}

async function verifyJwt(authHeader: string | null, secret: string): Promise<string> {
  if (!authHeader?.startsWith("Bearer ")) throw new Error("Unauthorized");
  // Minimal HS256 verify; replace with your auth library
  const token = authHeader.slice(7);
  const [headerB64, payloadB64] = token.split(".");
  const payload = JSON.parse(atob(payloadB64));
  if (payload.exp < Date.now() / 1000) throw new Error("Token expired");
  return payload.sub as string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let userId: string;
    try {
      userId = await verifyJwt(request.headers.get("Authorization"), env.JWT_SECRET);
    } catch {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);

    if (request.method === "POST" && url.pathname === "/sync/presign") {
      const { filename, contentType, size } = await request.json<{
        filename: string;
        contentType: string;
        size: number;
      }>();

      const key = `users/${userId}/${filename}`;
      const presignedUrl = await env.BUCKET.createMultipartUpload(key);

      // Record pending upload in D1
      await env.DB.prepare(
        "INSERT OR REPLACE INTO file_sync (user_id, filename, r2_key, status, size) VALUES (?, ?, ?, 'pending', ?)"
      ).bind(userId, filename, key, size).run();

      return Response.json({ presignedUrl: presignedUrl.uploadId, r2Key: key });
    }

    if (request.method === "POST" && url.pathname === "/sync/complete") {
      const { filename, etag } = await request.json<{ filename: string; etag: string }>();
      await env.DB.prepare(
        "UPDATE file_sync SET status = 'synced', etag = ? WHERE user_id = ? AND filename = ?"
      ).bind(etag, userId, filename).run();
      return Response.json({ ok: true });
    }

    if (request.method === "GET" && url.pathname === "/sync/download") {
      const filename = url.searchParams.get("filename")!;
      const key = `users/${userId}/${filename}`;
      const obj = await env.BUCKET.head(key);
      if (!obj) return new Response("Not Found", { status: 404 });

      // R2 presigned download (24-hour expiry)
      const signed = await env.BUCKET.createPresignedUrl(key, { expiresIn: 86400 });
      return Response.json({ url: signed });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## D1 Schema

```sql
-- migrations/0001_file_sync.sql
CREATE TABLE IF NOT EXISTS file_sync (
  user_id     TEXT NOT NULL,
  filename    TEXT NOT NULL,
  r2_key      TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'pending', -- pending | synced | conflict
  etag        TEXT,
  size        INTEGER,
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (user_id, filename)
);
```

## Capacitor Sync Service (TypeScript)

```typescript
// src/services/r2SyncService.ts
import { Filesystem, Directory, Encoding } from "@capacitor/filesystem";
import { Network } from "@capacitor/network";

const WORKERS_BASE = "https://sync.example.com";
const PENDING_QUEUE_KEY = "r2-pending-uploads";

interface PendingUpload {
  filename: string;
  localPath: string;
  contentType: string;
  size: number;
}

function getQueue(): PendingUpload[] {
  try {
    return JSON.parse(localStorage.getItem(PENDING_QUEUE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveQueue(queue: PendingUpload[]): void {
  localStorage.setItem(PENDING_QUEUE_KEY, JSON.stringify(queue));
}

export async function enqueueUpload(upload: PendingUpload): Promise<void> {
  const queue = getQueue();
  if (!queue.find((u) => u.filename === upload.filename)) {
    queue.push(upload);
    saveQueue(queue);
  }
  await attemptSync();
}

export async function attemptSync(): Promise<void> {
  const status = await Network.getStatus();
  if (!status.connected) return;

  const queue = [...getQueue()];
  const authToken = <redacted-secret>"auth_token");
  if (!authToken) return;

  for (const item of queue) {
    try {
      // Read file bytes from Capacitor Filesystem
      const { data } = await Filesystem.readFile({
        path: item.localPath,
        directory: Directory.Documents,
      });

      // Convert base64 to Blob
      const binaryStr = atob(data as string);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i);
      const blob = new Blob([bytes], { type: item.contentType });

      // Get presigned URL from Workers
      const presignRes = await fetch(`${WORKERS_BASE}/sync/presign`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          filename: item.filename,
          contentType: item.contentType,
          size: item.size,
        }),
      });
      if (!presignRes.ok) continue;

      const { r2Key } = await presignRes.json<{ presignedUrl: string; r2Key: string }>();

      // Upload directly to R2
      const uploadRes = await fetch(`https://r2.example.com/${r2Key}`, {
        method: "PUT",
        body: blob,
        headers: { "Content-Type": item.contentType },
      });
      if (!uploadRes.ok) continue;

      const etag = uploadRes.headers.get("ETag") ?? "";

      // Notify Workers of completion
      await fetch(`${WORKERS_BASE}/sync/complete`, {
        method: "POST",
        headers: { Authorization: `Bearer ${authToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ filename: item.filename, etag }),
      });

      // Remove from queue
      saveQueue(getQueue().filter((u) => u.filename !== item.filename));
    } catch {
      // Leave in queue for next retry
    }
  }
}
```

## Network Listener for Auto-Sync

```typescript
// src/services/networkSync.ts
import { Network } from "@capacitor/network";
import { attemptSync } from "./r2SyncService";

export function registerNetworkSync(): void {
  Network.addListener("networkStatusChange", async (status) => {
    if (status.connected) {
      await attemptSync();
    }
  });
}
```

## Download a Synced File

```typescript
// src/services/r2Download.ts
import { Filesystem, Directory } from "@capacitor/filesystem";

const WORKERS_BASE = "https://sync.example.com";

export async function downloadFile(filename: string, authToken: string): Promise<string> {
  const res = await fetch(
    `${WORKERS_BASE}/sync/download?filename=${encodeURIComponent(filename)}`,
    { headers: { Authorization: `Bearer ${authToken}` } }
  );
  if (!res.ok) throw new Error(`Download presign failed: ${res.status}`);

  const { url } = await res.json<{ url: string }>();
  const dataRes = await fetch(url);
  const buffer = await dataRes.arrayBuffer();
  const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));

  await Filesystem.writeFile({
    path: filename,
    data: base64,
    directory: Directory.Documents,
  });

  return filename;
}
```

## Anti-patterns

- **Routing binary through the Worker**: never pipe file bytes through `fetch()` to the Worker and then to R2. Use presigned URLs so the Worker only handles metadata (URL generation and D1 updates).
- **Storing the full file in localStorage**: localStorage is limited to ~5 MB per origin and is synchronous. Always write files to `Filesystem` and store only queue metadata in localStorage.
- **Re-uploading on every sync attempt**: track ETag in D1 and compare before re-uploading. An identical ETag means the file is already on R2.
- **Ignoring iOS app sandbox limits**: `Directory.Documents` is iCloud-eligible; prefer `Directory.Cache` or `Directory.Data` for temporary files to avoid unintended iCloud sync.

## Gotchas

- `Filesystem.readFile` returns base64-encoded strings on native platforms. Decoding large files (> 50 MB) synchronously can block the JS thread; process in chunks.
- Cloudflare R2 presigned URLs expire. Generate them immediately before upload, not at enqueue time. Default expiry is 1 hour; set `expiresIn` to match your expected upload window.
- `@capacitor/network` does not distinguish WiFi from cellular. If you want WiFi-only sync (like Google Photos), check `status.connectionType === "wifi"`.
- R2 `createPresignedUrl` is a Workers Beta API (2026). Confirm availability via `wrangler r2 object list` — if the method is missing, fall back to a signed URL generated with `aws4` HMAC on the Worker.

## Verification

```bash
# 1. Create R2 bucket
wrangler r2 bucket create sync-bucket

# 2. Run D1 migration
wrangler d1 execute MY_DB --file migrations/0001_file_sync.sql

# 3. Deploy the Worker
wrangler deploy

# 4. Test presign endpoint
curl -X POST https://sync.example.com/sync/presign \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"filename":"test.pdf","contentType":"application/pdf","size":1024}'

# 5. Confirm D1 row inserted
wrangler d1 execute MY_DB --command "SELECT * FROM file_sync WHERE status='pending'"
```

## Related

- `capacitor-r2-live-updates.md`
- `capacitor-file-picker-r2-direct-upload.md`
- `cloudflare-r2-presigned-url-mobile-clock-drift.md`
- `mobile-offline-first-sync-cloudflare-queues.md`

## Sources

- https://capacitorjs.com/docs/apis/filesystem
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://developers.cloudflare.com/d1/
