# Origin Private File System (OPFS) — High-Performance Local Storage on Cloudflare Pages

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to store large binary files — SQLite databases, user-generated assets,
downloaded media — directly in the browser without a round-trip to the server, and with
performance better than IndexedDB. You also want to sync those files to Cloudflare R2
when the user is online, keeping the local copy as the source of truth for offline use.

## Context

The **Origin Private File System** (OPFS) is part of the File System API (not the File
System Access API for user-visible files). It gives each origin a sandboxed, private
directory tree backed by native file storage. Unlike IndexedDB, OPFS supports
**synchronous** reads/writes via `FileSystemSyncAccessHandle` inside a Web Worker,
making it fast enough to host an in-browser SQLite database (via `@sqlite.org/sqlite-wasm`
or `wa-sqlite`).

OPFS is supported in Chrome/Edge 102+, Firefox 111+, Safari 16+. Cloudflare Pages has
no special configuration requirements — OPFS is a pure browser API.

## Accessing OPFS from the Main Thread (Async)

```typescript
// lib/opfs.ts

/** Returns the OPFS root directory handle. */
export async function getOPFSRoot(): Promise<FileSystemDirectoryHandle> {
  return navigator.storage.getDirectory();
}

/** Write a Blob / File to OPFS at the given path (relative to root). */
export async function writeFile(path: string, data: Blob | ArrayBuffer): Promise<void> {
  const root = await getOPFSRoot();
  // Support nested paths like "cache/videos/clip.mp4"
  const parts = path.split('/');
  const fileName = parts.pop()!;
  let dir = root;
  for (const part of parts) {
    dir = await dir.getDirectoryHandle(part, { create: true });
  }
  const fileHandle = await dir.getFileHandle(fileName, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(data);
  await writable.close();
}

/** Read a file from OPFS as an ArrayBuffer. */
export async function readFile(path: string): Promise<ArrayBuffer> {
  const root = await getOPFSRoot();
  const parts = path.split('/');
  const fileName = parts.pop()!;
  let dir = root;
  for (const part of parts) {
    dir = await dir.getDirectoryHandle(part);
  }
  const fileHandle = await dir.getFileHandle(fileName);
  const file = await fileHandle.getFile();
  return file.arrayBuffer();
}

/** Delete a file from OPFS. */
export async function deleteFile(path: string): Promise<void> {
  const root = await getOPFSRoot();
  const parts = path.split('/');
  const fileName = parts.pop()!;
  let dir = root;
  for (const part of parts) {
    dir = await dir.getDirectoryHandle(part);
  }
  await dir.removeEntry(fileName);
}
```

## High-Performance Access via FileSystemSyncAccessHandle in a Worker

Synchronous handles are only available inside dedicated Web Workers — they give ~10×
faster I/O than the async API by bypassing the Promise overhead:

```typescript
// workers/opfs-worker.ts  (bundled as a Web Worker, NOT a Cloudflare Worker)
/// <reference lib="webworker" />

self.onmessage = async (e: MessageEvent<{ op: string; path: string; data?: ArrayBuffer }>) => {
  const { op, path, data } = e.data;
  const root = await navigator.storage.getDirectory();

  try {
    if (op === 'write' && data) {
      const fileHandle = await root.getFileHandle(path, { create: true });
      const syncHandle = await fileHandle.createSyncAccessHandle();
      syncHandle.truncate(0);
      syncHandle.write(new Uint8Array(data), { at: 0 });
      syncHandle.flush();
      syncHandle.close();
      self.postMessage({ op, path, ok: true });
    } else if (op === 'read') {
      const fileHandle = await root.getFileHandle(path);
      const syncHandle = await fileHandle.createSyncAccessHandle();
      const size = syncHandle.getSize();
      const buf = new ArrayBuffer(size);
      syncHandle.read(new Uint8Array(buf), { at: 0 });
      syncHandle.close();
      self.postMessage({ op, path, ok: true, data: buf }, [buf]);
    }
  } catch (err) {
    self.postMessage({ op, path, ok: false, error: String(err) });
  }
};
```

```typescript
// lib/opfs-worker-client.ts — typed wrapper for main thread
let worker: Worker | null = null;

function getWorker(): Worker {
  if (!worker) {
    worker = new Worker(new URL('../workers/opfs-worker.ts', import.meta.url), {
      type: 'module',
    });
  }
  return worker;
}

type WorkerResult = { op: string; path: string; ok: boolean; data?: ArrayBuffer; error?: string };

export function opfsWrite(path: string, data: ArrayBuffer): Promise<void> {
  return new Promise((resolve, reject) => {
    const w = getWorker();
    const handler = (e: MessageEvent<WorkerResult>) => {
      if (e.data.path !== path || e.data.op !== 'write') return;
      w.removeEventListener('message', handler);
      e.data.ok ? resolve() : reject(new Error(e.data.error));
    };
    w.addEventListener('message', handler);
    w.postMessage({ op: 'write', path, data }, [data]);
  });
}

export function opfsRead(path: string): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const w = getWorker();
    const handler = (e: MessageEvent<WorkerResult>) => {
      if (e.data.path !== path || e.data.op !== 'read') return;
      w.removeEventListener('message', handler);
      e.data.ok && e.data.data ? resolve(e.data.data) : reject(new Error(e.data.error));
    };
    w.addEventListener('message', handler);
    w.postMessage({ op: 'read', path });
  });
}
```

## Syncing OPFS Files to Cloudflare R2

Use a Service Worker background sync or a manual upload from the main thread. The
pattern below does a simple presigned-URL upload:

```typescript
// lib/r2-sync.ts
import { readFile } from './opfs';

export async function syncFileToR2(
  localPath: string,
  r2Key: string,
  getPresignedUrl: (key: string) => Promise<string>,
): Promise<void> {
  const buf = await readFile(localPath);
  const url = await getPresignedUrl(r2Key);

  const resp = await fetch(url, {
    method: 'PUT',
    body: buf,
    headers: { 'Content-Type': 'application/octet-stream' },
  });

  if (!resp.ok) {
    throw new Error(`R2 upload failed: ${resp.status} ${resp.statusText}`);
  }
}

export async function syncFileFromR2(
  r2Url: string,
  localPath: string,
): Promise<void> {
  const resp = await fetch(r2Url);
  if (!resp.ok) throw new Error(`R2 download failed: ${resp.status}`);
  const buf = await resp.arrayBuffer();
  const { writeFile } = await import('./opfs');
  await writeFile(localPath, buf);
}
```

Gate uploads with `navigator.onLine` and queue them via `BackgroundSync` for offline
resilience.

## Storage Quota

OPFS shares the origin's storage quota with IndexedDB and Cache Storage. Check before
writing large files:

```typescript
export async function checkOPFSQuota(): Promise<{ used: number; quota: number; available: number }> {
  const { usage = 0, quota = 0 } = await navigator.storage.estimate();
  return { used: usage, quota, available: quota - usage };
}
```

If `available < requiredBytes`, prompt the user or fall back to server-only storage.

## Anti-patterns

- **Reading large files on the main thread with the async API.** Each chunk requires a
  round-trip through the Promise queue. Use a Web Worker with `FileSystemSyncAccessHandle`
  for files > 1 MB.
- **Keeping `FileSystemSyncAccessHandle` open across awaits.** The sync handle holds an
  exclusive lock. Open → read/write → `close()` in a single synchronous block.
- **Using OPFS as a permanent user-visible store.** The browser can evict OPFS data
  under storage pressure. Always sync critical data to R2 / the server.
- **Not requesting `persistent` storage for critical data.** Call
  `navigator.storage.persist()` to prevent eviction; the browser may prompt the user.

## Gotchas

- `FileSystemSyncAccessHandle` is only available in **dedicated** Web Workers (not
  shared workers, service workers, or the main thread).
- Paths in OPFS use `/` as a separator but the API is handle-based — you must traverse
  each directory with `getDirectoryHandle`, not pass a full path string.
- In Safari 16, `createSyncAccessHandle` is available but does not support the `at`
  offset option for reads; always `seek` manually if you need Safari 16 support.
- OPFS data does **not** appear in DevTools → Application → Storage when inspecting
  standard file system entries; use the DevTools Storage bucket panel (Chrome 108+).
- SSR / Node: `navigator.storage` does not exist. Gate all OPFS calls behind
  `typeof navigator !== 'undefined' && 'storage' in navigator`.

## Verification

1. Chrome DevTools → Application → Storage → Origin Private File System: verify files
   appear after write operations.
2. Call `checkOPFSQuota()` before and after writing a 50 MB file; confirm `used`
   increases by ~50 MB.
3. Disable network in DevTools; verify the app reads from OPFS without errors.
4. Re-enable network; trigger `syncFileToR2`; inspect the R2 bucket via Cloudflare
   dashboard to confirm the file landed.
5. Call `navigator.storage.persist()` and check the return value (`true` = granted).

## Related

- `browser-indexeddb-patterns.md`
- `browser-file-system-access.md`
- `cloudflare-r2-presigned-upload-frontend.md`
- `pwa-service-worker-cloudflare-pages.md`
- `browser-storage-quota.md`
- `wasm-cloudflare-workers-image-transform.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/File_System_API/Origin_private_file_system
- https://web.dev/articles/origin-private-file-system
- https://sqlite.org/wasm/doc/tip/persistence.md
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://storage.spec.whatwg.org/
