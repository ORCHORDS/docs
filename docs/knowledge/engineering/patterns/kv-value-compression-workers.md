# KV Value Compression Pattern — Workers + KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker caches large JSON payloads (product catalogs, permission trees, configuration blobs) in KV. Storage costs climb because KV bills per GB stored, and read latency increases because large values take longer to deserialize. Some payloads exceed KV's 25 MB per-value limit. Compressing values before storing them reduces storage size by 60–90 % for typical JSON and keeps reads fast.

## Context

- Cloudflare Workers have access to the Web Compression Streams API (`CompressionStream`, `DecompressionStream`) natively — no npm packages required.
- KV values can be stored as `ArrayBuffer` (binary), which is ideal for compressed bytes.
- The pattern wraps a KV namespace in a thin `CompressedKV` adapter that is transparent to the rest of the codebase.
- Gzip compression is used because it is universally supported and produces good ratios for JSON. Deflate-raw and zstd are alternatives when available.
- A magic prefix byte (`0x1f 0x8b` for gzip) lets the reader detect whether a legacy uncompressed value is being read and handle it gracefully.

---

## Compression Utilities

```typescript
// src/lib/compress.ts

/** Compress a UTF-8 string to a gzip ArrayBuffer. */
export async function gzipEncode(input: string): Promise<ArrayBuffer> {
  const encoded = new TextEncoder().encode(input);
  const cs = new CompressionStream('gzip');
  const writer = cs.writable.getWriter();
  writer.write(encoded);
  writer.close();
  return new Response(cs.readable).arrayBuffer();
}

/** Decompress a gzip ArrayBuffer back to a UTF-8 string. */
export async function gzipDecode(input: ArrayBuffer): Promise<string> {
  const ds = new DecompressionStream('gzip');
  const writer = ds.writable.getWriter();
  writer.write(input);
  writer.close();
  const buffer = await new Response(ds.readable).arrayBuffer();
  return new TextDecoder().decode(buffer);
}

/** Detect gzip magic bytes (1f 8b). */
export function isGzipped(buf: ArrayBuffer): boolean {
  const view = new Uint8Array(buf, 0, 2);
  return view[0] === 0x1f && view[1] === 0x8b;
}
```

---

## CompressedKV Adapter

```typescript
// src/lib/compressed-kv.ts
import { gzipEncode, gzipDecode, isGzipped } from './compress';

export interface CompressedKVOptions {
  /** Only compress values larger than this byte count. Default: 512. */
  minSizeBytes?: number;
}

export class CompressedKV {
  private kv: KVNamespace;
  private minSize: number;

  constructor(kv: KVNamespace, options: CompressedKVOptions = {}) {
    this.kv = kv;
    this.minSize = options.minSizeBytes ?? 512;
  }

  async put(
    key: string,
    value: string,
    options?: KVNamespacePutOptions
  ): Promise<void> {
    const byteLength = new TextEncoder().encode(value).byteLength;

    if (byteLength >= this.minSize) {
      const compressed = await gzipEncode(value);
      await this.kv.put(key, compressed, options);
    } else {
      // Small values: store as plain text, cheaper to decompress
      await this.kv.put(key, value, options);
    }
  }

  async get(key: string): Promise<string | null> {
    // Try reading as ArrayBuffer first to detect compression
    const raw = await this.kv.get(key, { type: 'arrayBuffer' });
    if (raw === null) return null;

    if (isGzipped(raw)) {
      return gzipDecode(raw);
    }

    // Uncompressed: decode as UTF-8 text
    return new TextDecoder().decode(raw);
  }

  async getJSON<T>(key: string): Promise<T | null> {
    const text = await this.get(key);
    return text === null ? null : (JSON.parse(text) as T);
  }

  async delete(key: string): Promise<void> {
    await this.kv.delete(key);
  }
}
```

---

## Usage in a Worker Handler

```typescript
// src/handlers/catalog.ts
import { CompressedKV } from '../lib/compressed-kv';

const CATALOG_TTL = 300; // 5 minutes

export async function handleGetCatalog(
  _request: Request,
  env: Env
): Promise<Response> {
  const ckv = new CompressedKV(env.KV, { minSizeBytes: 256 });
  const cacheKey = 'catalog:v3:all';

  let catalog = await ckv.getJSON<ProductCatalog>(cacheKey);

  if (!catalog) {
    // Fetch from origin / D1
    catalog = await fetchCatalogFromD1(env.DB);

    // Store compressed; fire-and-forget — don't block the response
    env.ctx.waitUntil(
      ckv.put(cacheKey, JSON.stringify(catalog), {
        expirationTtl: CATALOG_TTL,
      })
    );
  }

  return Response.json(catalog);
}
```

---

## Batch Migration — Recompress Existing Plain-text Values

```typescript
// src/scripts/migrate-compress.ts
// Run once via `wrangler dev` or a one-off Worker invocation.
export async function migrateToCompressed(
  kv: KVNamespace,
  prefix: string
): Promise<{ migrated: number; skipped: number }> {
  const ckv = new CompressedKV(kv);
  let cursor: string | undefined;
  let migrated = 0;
  let skipped = 0;

  do {
    const list = await kv.list({ prefix, cursor, limit: 100 });

    for (const key of list.keys) {
      const raw = await kv.get(key.name, { type: 'arrayBuffer' });
      if (!raw || isGzipped(raw)) {
        skipped++;
        continue;
      }

      const text = new TextDecoder().decode(raw);
      if (new TextEncoder().encode(text).byteLength < 512) {
        skipped++;
        continue;
      }

      // Re-store compressed, preserving expiration metadata
      await ckv.put(key.name, text, {
        expirationTtl: key.expiration
          ? Math.max(60, key.expiration - Math.floor(Date.now() / 1000))
          : undefined,
      });
      migrated++;
    }

    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);

  return { migrated, skipped };
}
```

---

## Compression Ratio Instrumentation

```typescript
// src/lib/compress.ts  (addition)
export async function gzipEncodeWithStats(
  input: string
): Promise<{ buffer: ArrayBuffer; originalBytes: number; compressedBytes: number; ratio: number }> {
  const originalBytes = new TextEncoder().encode(input).byteLength;
  const buffer = await gzipEncode(input);
  const compressedBytes = buffer.byteLength;
  return {
    buffer,
    originalBytes,
    compressedBytes,
    ratio: compressedBytes / originalBytes,
  };
}
```

---

## Anti-patterns

- **Compressing every value regardless of size**: small values (< 200 bytes) often expand after gzip header overhead. Use a `minSizeBytes` threshold.
- **Storing the encoding scheme in a separate metadata key**: this doubles KV reads. Detect compression via magic bytes instead.
- **Using `type: 'text'` on a compressed value**: KV will try to decode binary gzip bytes as UTF-8 and return garbled text or `null`. Always use `type: 'arrayBuffer'` and detect compression at read time.
- **Blocking the response on compression**: compression is async and can take 1–5 ms on large payloads. Use `waitUntil` for write-path compression to avoid adding latency to the response.
- **Compressing already-compressed binary content**: images, videos, or other pre-compressed blobs see negligible gains from a second pass and add CPU overhead.

## Gotchas

- `CompressionStream('gzip')` is available in Workers runtime ≥ 2023-03-01 compatibility date. Verify your `compatibility_date` in `wrangler.toml`.
- KV `arrayBuffer` reads return an `ArrayBuffer`, not a `Buffer`. Use `new Uint8Array(buf)` for byte-level access.
- Gzip decompression on a 1 MB payload takes roughly 2–5 ms of CPU time in Workers. For extremely hot paths consider an in-memory module-scope cache in addition to KV.
- KV list operations do not return the value; you must do a separate `get` per key. Batch migrations over large namespaces can be slow — run them during off-peak hours.

## Verification

```bash
# Write a large catalog object to KV and verify compressed size
wrangler kv key put --namespace-id=<id> "catalog:v3:all" \
  "$(node -e 'console.log(JSON.stringify(require("./fixtures/catalog.json")))')"

# Check stored size vs raw JSON size
wrangler kv key get --namespace-id=<id> "catalog:v3:all" --binary | wc -c
node -e 'console.log(Buffer.from(JSON.stringify(require("./fixtures/catalog.json"))).length)'
```

## Related

- `multi-layer-cache-workers-cache-api-kv-d1.md`
- `cache-aside-kv-d1-fallback.md`
- `read-through-cache-workers-kv-d1.md`
- `write-through-cache-workers-kv-d1.md`

## Sources

- Cloudflare Workers docs — Compression Streams: https://developers.cloudflare.com/workers/runtime-apis/streams/compressionstream/
- Cloudflare KV docs — Values and limits: https://developers.cloudflare.com/kv/platform/limits/
- IETF RFC 1952 — GZIP file format specification (magic bytes 1f 8b)
