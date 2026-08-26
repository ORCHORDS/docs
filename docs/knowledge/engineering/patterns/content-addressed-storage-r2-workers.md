# Content-Addressed Storage with R2 and Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Static assets — compiled JS bundles, generated PDFs, avatar images, audio waveforms —
are re-uploaded on every deploy or user action even when the content is identical to
what is already in R2. Cache invalidation is painful because URLs change when backends
cycle. You want immutable, de-duplicated object storage where identical bytes always
live at the same URL and can be cached forever by CDN and browsers.

## Context

Content-Addressed Storage (CAS) derives the storage key from the *content itself* — a
cryptographic hash of the bytes — rather than from a mutable name or timestamp. The
key property is **immutability**: if the key exists the object is guaranteed to be
correct because the key is the hash. Uploading the same content twice is a no-op after
the first write.

On Cloudflare the combination of R2 (object storage) + Workers (hash computation +
routing) + KV or D1 (human-readable alias → hash mapping) produces a full CAS layer:

- **Content objects** live at `cas/<hex-hash>` in R2 — `Cache-Control: immutable`.
- **Aliases** (`assets/logo.png`, `bundles/app.js`) live in KV or D1 as `alias → hash`.
- **Workers** serve `GET /asset/<alias>` by resolving the alias to a hash, then
  streaming the R2 object with far-future cache headers.

## Computing the Content Hash

```typescript
// hash.ts
export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// For streaming uploads, hash incrementally using a TransformStream accumulator
export async function hashStream(
  stream: ReadableStream<Uint8Array>,
): Promise<{ hash: string; body: ArrayBuffer }> {
  const chunks: Uint8Array[] = [];
  const reader = stream.getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  const totalLength = chunks.reduce((n, c) => n + c.byteLength, 0);
  const merged = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  const buffer = merged.buffer;
  return { hash: await sha256Hex(buffer), body: buffer };
}
```

## Storing Objects (Put-if-Absent)

```typescript
// store.ts
import { sha256Hex } from './hash';

interface StoreResult {
  hash: string;
  casKey: string;
  existed: boolean;
}

export async function storeContent(
  content: ArrayBuffer,
  contentType: string,
  r2: R2Bucket,
): Promise<StoreResult> {
  const hash = await sha256Hex(content);
  const casKey = `cas/${hash}`;

  // Check existence before writing — R2 head is cheaper than put
  const head = await r2.head(casKey);
  if (head !== null) {
    return { hash, casKey, existed: true };
  }

  await r2.put(casKey, content, {
    httpMetadata: {
      contentType,
      // Immutable objects can be cached forever — the key changes when content changes
      cacheControl: 'public, max-age=31536000, immutable',
    },
    customMetadata: {
      sha256: hash,
      storedAt: new Date().toISOString(),
    },
  });

  return { hash, casKey, existed: false };
}

// Register a human-readable alias → hash mapping
export async function setAlias(
  alias: string,
  hash: string,
  kv: KVNamespace,
): Promise<void> {
  await kv.put(`alias:${alias}`, hash, {
    metadata: { updatedAt: new Date().toISOString() },
  });
}
```

## Serving Aliased Assets via Worker

```typescript
// serve.ts — Cloudflare Worker fetch handler
export interface Env {
  ASSET_BUCKET: R2Bucket;
  ALIAS_KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // /asset/<alias>  →  resolve alias → cas key → R2 object
    const aliasMatch = url.pathname.match(/^\/asset\/(.+)$/);
    if (aliasMatch) {
      return serveAlias(aliasMatch[1], request, env);
    }

    // /cas/<hash>  →  direct content address lookup
    const casMatch = url.pathname.match(/^\/cas\/([0-9a-f]{64})$/);
    if (casMatch) {
      return serveCasObject(casMatch[1], request, env);
    }

    return new Response('Not Found', { status: 404 });
  },
};

async function serveAlias(alias: string, request: Request, env: Env): Promise<Response> {
  const hash = await env.ALIAS_KV.get(`alias:${alias}`);
  if (!hash) return new Response('Alias not found', { status: 404 });

  const response = await serveCasObject(hash, request, env);
  // Alias responses use short cache with stale-while-revalidate
  const newHeaders = new Headers(response.headers);
  newHeaders.set('Cache-Control', 'public, max-age=60, stale-while-revalidate=3600');
  newHeaders.set('X-Content-Hash', hash);
  return new Response(response.body, { status: response.status, headers: newHeaders });
}

async function serveCasObject(hash: string, request: Request, env: Env): Promise<Response> {
  const casKey = `cas/${hash}`;

  // Support conditional requests: ETag is the hash itself
  const ifNoneMatch = request.headers.get('If-None-Match');
  if (ifNoneMatch === `"${hash}"`) {
    return new Response(null, { status: 304 });
  }

  const object = await env.ASSET_BUCKET.get(casKey, {
    range: request.headers.get('Range') ? { suffix: 0 } : undefined,
  });

  if (!object) return new Response('Object not found', { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('ETag', `"${hash}"`);
  headers.set('Cache-Control', 'public, max-age=31536000, immutable');
  headers.set('X-Content-Hash', hash);

  return new Response(object.body, { headers });
}
```

## Batch De-duplication During Deploy

```typescript
// deploy.ts — run from a CI step or Wrangler custom command
interface AssetManifest {
 // alias → local file path
}

export async function deployAssets(
  manifest: AssetManifest,
  r2: R2Bucket,
  kv: KVNamespace,
): Promise<{ uploaded: number; skipped: number }> {
  let uploaded = 0;
  let skipped = 0;

  for (const [alias, filePath] of Object.entries(manifest)) {
    // In a real deploy pipeline, read from disk or a build artifact
    const content: ArrayBuffer = await fetchLocalFile(filePath);
    const { hash, existed } = await storeContent(content, guessMimeType(filePath), r2);
    await setAlias(alias, hash, kv);

    if (existed) skipped++;
    else uploaded++;
  }

  return { uploaded, skipped };
}

function guessMimeType(path: string): string {
  if (path.endsWith('.js')) return 'application/javascript';
  if (path.endsWith('.css')) return 'text/css';
  if (path.endsWith('.png')) return 'image/png';
  if (path.endsWith('.webp')) return 'image/webp';
  return 'application/octet-stream';
}

declare function fetchLocalFile(path: string): Promise<ArrayBuffer>;
```

## Garbage Collection of Unreferenced Objects

```typescript
// gc.ts — scheduled cron Worker
export async function collectGarbage(
  r2: R2Bucket,
  kv: KVNamespace,
  db: D1Database,
): Promise<void> {
  // 1. Collect all known alias hashes from KV
  const liveHashes = new Set<string>();
  let cursor: string | undefined;
  do {
    const page = await kv.list({ prefix: 'alias:', cursor });
    for (const key of page.keys) {
      const hash = await kv.get(key.name);
      if (hash) liveHashes.add(hash);
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  // 2. Walk all CAS objects in R2
  let r2Cursor: string | undefined;
  const toDelete: string[] = [];
  do {
    const listed = await r2.list({ prefix: 'cas/', cursor: r2Cursor, limit: 1000 });
    for (const obj of listed.objects) {
      const hash = obj.key.replace('cas/', '');
      if (!liveHashes.has(hash)) {
        toDelete.push(obj.key);
      }
    }
    r2Cursor = listed.truncated ? listed.cursor : undefined;
  } while (r2Cursor);

  if (toDelete.length > 0) {
    await r2.delete(toDelete);
    console.log({ event: 'cas_gc', deleted: toDelete.length });
  }
}
```

## Anti-patterns

- **Mutable CAS keys** — never overwrite an existing `cas/<hash>` object with different
  bytes; the entire guarantee is that the key uniquely identifies the content forever.
- **Using insecure hashes (MD5, CRC32)** — collision probability matters at scale and
  MD5/CRC32 are not collision-resistant. Use SHA-256 at minimum.
- **Serving CAS objects without immutable cache headers** — the point of CAS is that
  the URL never changes for the same content, so CDN/browser caching must be aggressive.
- **Storing aliases only in-memory or in KV without D1 audit trail** — alias history
  (what hash alias X pointed to a week ago) is valuable for debugging and rollback.
- **Running GC too aggressively** — a newly uploaded object may not have an alias
  registered yet (race between put and setAlias). Add a grace period of at least
  5 minutes before considering an unaliased object eligible for deletion.

## Gotchas

- `crypto.subtle.digest` is available in Workers but is asynchronous; large files
  must be fully buffered before hashing (Workers do not have a streaming hash API).
  For objects above ~50 MB, consider a chunked upload + manifest hash approach.
- R2 `head` returns `null` for non-existent objects — do not confuse with `undefined`.
- KV `list` paginates at 1000 keys per call; always loop until `list_complete === true`.
- `object.writeHttpMetadata(headers)` sets `Content-Type` from the stored metadata;
  if metadata was omitted on put the header will be missing from the response.
- R2 `delete` accepts up to 1000 keys per call; batch your GC deletes.

## Verification

```bash
# Upload an asset and verify the hash matches
HASH=$(sha256sum dist/app.js | awk '{print $1}')
curl -X PUT https://api.example.com/cas/$HASH \
  -H "Content-Type: application/javascript" \
  --data-binary @dist/app.js

# Resolve alias and confirm ETag matches hash
curl -sI https://cdn.example.com/asset/bundles/app.js \
  | grep -E 'ETag|X-Content-Hash'
# Expect: ETag: "<sha256>" and X-Content-Hash: <sha256>

# Verify immutable cache header
curl -sI https://cdn.example.com/cas/$HASH | grep Cache-Control
# Expect: public, max-age=31536000, immutable
```

## Related

- `cache-aside-kv-d1-fallback.md`
- `write-behind-cache-kv-d1.md`
- `claim-check-pattern-r2-queues.md`
- `feature-cookbook-cdn.md`
- `zero-downtime-db-migration.md`

## Sources

- IPFS Content Addressing — https://docs.ipfs.tech/concepts/content-addressing/
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Web Crypto API (SubtleCrypto) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
- Cloudflare KV — https://developers.cloudflare.com/kv/api/list-key-value-pairs/
