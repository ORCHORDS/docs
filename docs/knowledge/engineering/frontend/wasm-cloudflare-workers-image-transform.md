# WebAssembly in Cloudflare Workers for Frontend Image Processing

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your frontend needs server-side image resizing and format conversion (WebP/AVIF) at the edge — without the latency of routing through an origin server or the cost of a dedicated image CDN add-on.

## Context
Cloudflare Workers can import and instantiate WebAssembly modules at startup. Libraries compiled to WASM — such as `@cf-wasm/photon`, custom Rust codecs built with `wasm-pack`, or C-based image libraries — run inside the V8 isolate with near-native speed. Transformed images are cached in Cloudflare's CDN tier via `caches.default`, so repeat requests for the same transform parameters never re-invoke the WASM module. This replaces paid image-CDN add-ons when custom transform logic is needed.

## Wrangler Configuration

```toml
# wrangler.toml
name = "image-transform"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

# Wrangler bundles *.wasm as WebAssembly modules — importable directly in TS
[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]

[[r2_buckets]]
binding = "IMAGES"
bucket_name = "my-images"
```

```typescript
// src/worker.ts — WASM module imported at build time by Wrangler
import resizeWasm from './codecs/resize.wasm';

// Instantiate once per isolate lifetime — reuse across requests
let wasmExports: WebAssembly.Exports | null = null;

async function getWasm(): Promise<WebAssembly.Exports> {
  if (wasmExports) return wasmExports;
  const { instance } = await WebAssembly.instantiate(resizeWasm, {});
  wasmExports = instance.exports;
  return wasmExports;
}
```

## Request Parsing and Cache Key

```typescript
// src/params.ts
export interface TransformParams {
  key: string;
  width: number;
  height: number;
  format: 'webp' | 'jpeg' | 'png';
  quality: number;
}

export function parseParams(url: URL): TransformParams | null {
  const key = url.searchParams.get('key');
  const width = Number(url.searchParams.get('w'));
  const height = Number(url.searchParams.get('h'));
  const format = (url.searchParams.get('fmt') ?? 'webp') as TransformParams['format'];
  const quality = Number(url.searchParams.get('q') ?? 80);

  if (!key || !width || !height || width > 4096 || height > 4096) return null;
  if (!['webp', 'jpeg', 'png'].includes(format)) return null;
  if (quality < 1 || quality > 100) return null;
  return { key, width, height, format, quality };
}

export const cacheKey = (p: TransformParams) =>
  `https://image-cache/${p.key}/${p.width}x${p.height}/${p.format}/${p.quality}`;
```

## WASM Transform Pipeline

```typescript
// src/transform.ts
// Assumes a Rust/wasm-pack module exporting: alloc, dealloc, resize_encode, memory
// compile with: wasm-pack build --target no-modules --out-dir src/codecs

interface WasmExports {
  alloc: (size: number) => number;
  dealloc: (ptr: number, size: number) => void;
  resize_encode: (inPtr: number, inLen: number, w: number, h: number,
                  fmt: number, q: number, outPtrPtr: number, outLenPtr: number) => number;
  memory: WebAssembly.Memory;
}

const FMT = { webp: 0, jpeg: 1, png: 2 } as const;

export async function resizeImage(
  src: Uint8Array,
  width: number, height: number,
  format: 'webp' | 'jpeg' | 'png',
  quality: number,
  wasm: WasmExports
): Promise<Uint8Array> {
  const mem = new Uint8Array(wasm.memory.buffer);

  const inPtr = wasm.alloc(src.byteLength);
  mem.set(src, inPtr);

  const outPtrPtr = wasm.alloc(4);
  const outLenPtr = wasm.alloc(4);

  const status = wasm.resize_encode(inPtr, src.byteLength, width, height,
                                    FMT[format], quality, outPtrPtr, outLenPtr);
  if (status !== 0) {
    wasm.dealloc(inPtr, src.byteLength);
    throw new Error(`WASM resize failed: status ${status}`);
  }

  const view = new DataView(wasm.memory.buffer);
  const outPtr = view.getUint32(outPtrPtr, true);
  const outLen = view.getUint32(outLenPtr, true);
  const result = new Uint8Array(wasm.memory.buffer, outPtr, outLen).slice();

  wasm.dealloc(inPtr, src.byteLength);
  wasm.dealloc(outPtr, outLen);
  wasm.dealloc(outPtrPtr, 4);
  wasm.dealloc(outLenPtr, 4);
  return result;
}
```

## Worker Fetch Handler

```typescript
// src/worker.ts (continued)
import { parseParams, cacheKey } from './params';
import { resizeImage } from './transform';

export type Env = { IMAGES: R2Bucket };

const MIME: Record<string, string> = { webp: 'image/webp', jpeg: 'image/jpeg', png: 'image/png' };

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const params = parseParams(new URL(request.url));
    if (!params) return new Response('Invalid parameters', { status: 400 });

    const ck = new Request(cacheKey(params));
    const cached = await caches.default.match(ck);
    if (cached) return cached;

    const obj = await env.IMAGES.get(params.key);
    if (!obj) return new Response('Not found', { status: 404 });

    const wasm = await getWasm() as Parameters<typeof resizeImage>[5];
    const src = new Uint8Array(await obj.arrayBuffer());
    const out = await resizeImage(src, params.width, params.height, params.format, params.quality, wasm);

    const response = new Response(out, {
      headers: {
        'Content-Type': MIME[params.format],
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });

    ctx.waitUntil(caches.default.put(ck, response.clone()));
    return response;
  },
} satisfies ExportedHandler<Env>;
```

## Frontend URL Builder

```typescript
// src/lib/imageUrl.ts
const WORKER = 'https://image-transform.example.workers.dev';

export const imageUrl = ({
  key, width, height, format = 'webp', quality = 80,
}: { key: string; width: number; height: number; format?: string; quality?: number }) => {
  const u = new URL(WORKER);
  Object.entries({ key, w: width, h: height, fmt: format, q: quality })
    .forEach(([k, v]) => u.searchParams.set(k, String(v)));
  return u.toString();
};

// Usage:
// <img src={imageUrl({ key: 'products/shoe.jpg', width: 400, height: 400 })} />
```

## Anti-patterns
- Instantiating the WASM module on every request — compilation is expensive; cache in isolate-level scope
- Forgetting `dealloc()` after every `alloc()` — WASM linear memory has no GC; unbounded allocs OOM the isolate
- Caching to R2 instead of `caches.default` — R2 reads require a Worker call on every hit; CDN cache is served from the edge
- Not bounding `width`/`height` query params — uncapped dimensions enable memory-exhaustion attacks
- Using Workers for video transcoding — 30 s CPU limit and 128 MB memory make it unsuitable; use a queue-triggered worker with Durable Objects instead

## Gotchas
- Workers do not support `WebAssembly.compileStreaming()` — use `WebAssembly.instantiate(module, imports)` with the Wrangler-bundled binary
- WASM must target `wasm32-unknown-unknown`, not `wasm32-wasi` — Workers do not implement WASI
- `caches.default` cache keys must be full `https://` URLs — bare strings throw a `TypeError`
- `ctx.waitUntil(cache.put(...))` runs after the response is sent but still counts toward CPU time
- R2 `obj.arrayBuffer()` buffers the entire object in memory — stream large objects in chunks using `obj.body.getReader()` if the image may exceed a few MB

## Verification
```bash
# Compile Rust WASM
cargo build --target wasm32-unknown-unknown --release
cp target/wasm32-unknown-unknown/release/resize.wasm src/codecs/

npx wrangler deploy

curl -o /tmp/out.webp \
  "https://image-transform.example.workers.dev/?key=<redacted-secret>&w=400&h=400&fmt=webp&q=80"
file /tmp/out.webp  # → RIFF ... WEBP image

# Second request should be served from CDN cache (no Worker CPU usage)
curl -I "...same URL..." | grep cache-status
```

## Related
- [Image Format Selection WebP AVIF](image-format-selection-webp-avif.md)
- [HTML Srcset Responsive Images](html-srcset-responsive-images.md)
- [Cloudflare R2 Presigned Upload Frontend](cloudflare-r2-presigned-upload-frontend.md)
- [Browser Web Workers](browser-web-workers.md)

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://developers.cloudflare.com/workers/wrangler/configuration/#rules
- https://developers.cloudflare.com/workers/runtime-apis/cache/
- https://rustwasm.github.io/book/
