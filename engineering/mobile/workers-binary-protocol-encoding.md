# Binary Protocol Encoding for Mobile Bandwidth Optimization

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Mobile users on 3G or in areas with poor coverage experience slow list responses. JSON serialization overhead is measurable for large list endpoints (product catalogs, timeline feeds with 50–200 items). You want to serve MessagePack or a minimal hand-rolled Protocol Buffers encoding from Cloudflare Workers when the client requests it, reducing payload size and parse time without a separate binary endpoint.

## Context

Workers run in V8 isolates with `ArrayBuffer`, `Uint8Array`, and `TextEncoder`/`TextDecoder` available globally. There is no built-in MessagePack or Protobuf runtime. `@msgpack/msgpack` compiles cleanly with the Workers build toolchain (esbuild) and adds ~15 KB gzipped to the bundle.

Content-type negotiation follows the standard `Accept` header: clients that speak MessagePack send `Accept: application/msgpack`; the Worker inspects this and serializes accordingly. For large pre-encoded datasets stored in R2, the Worker can pipe the `ReadableStream` body directly without buffering into memory.

Cloudflare applies automatic gzip compression to `text/*` and `application/json` responses at the edge but not to `application/msgpack` or `application/protobuf`. Factor this in when comparing sizes: raw JSON vs raw MessagePack is misleading; the relevant comparison is gzip-JSON vs raw-MessagePack (they are close), or gzip-JSON vs gzip-MessagePack (MessagePack still wins by ~10–20%).

## Solution

```typescript
import { encode as msgpackEncode, decode as msgpackDecode } from '@msgpack/msgpack';

export interface Env {
  R2: R2Bucket;
}

// --- Content negotiation ---

type SerializationFormat = 'json' | 'msgpack';

function negotiateFormat(request: Request): SerializationFormat {
  const accept = request.headers.get('Accept') ?? '';
  if (accept.includes('application/msgpack')) return 'msgpack';
  return 'json';
}

// --- Serialization helpers ---

function serializeResponse(
  data: unknown,
  format: SerializationFormat,
  status = 200,
): Response {
  if (format === 'msgpack') {
    const encoded = msgpackEncode(data);
    return new Response(encoded, {
      status,
      headers: {
        'Content-Type': 'application/msgpack',
        'Content-Length': String(encoded.byteLength),
        'X-Serialization-Format': 'msgpack',
      },
    });
  }
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'X-Serialization-Format': 'json',
    },
  });
}

// --- Deserialize incoming request body (JSON or MessagePack) ---

async function deserializeBody(request: Request): Promise<unknown> {
  const ct = request.headers.get('Content-Type') ?? '';
  if (ct.includes('application/msgpack')) {
    const buffer = await request.arrayBuffer();
    return msgpackDecode(new Uint8Array(buffer));
  }
  return request.json();
}

// --- Payload size comparison utility ---

function measurePayloadSizes(data: unknown): {
  json_bytes: number;
  msgpack_bytes: number;
  reduction_percent: string;
} {
  const jsonBytes = new TextEncoder().encode(JSON.stringify(data)).byteLength;
  const msgpackBytes = msgpackEncode(data).byteLength;
  const pct = (((jsonBytes - msgpackBytes) / jsonBytes) * 100).toFixed(1);
  return { json_bytes: jsonBytes, msgpack_bytes: msgpackBytes, reduction_percent: `${pct}%` };
}

// --- Minimal hand-rolled Protobuf encoder ---
// Encodes a single message: { id: uint64, name: string, score: float32 }
// Field tags: 1=id (varint/wire-0), 2=name (len-delim/wire-2), 3=score (fixed32/wire-5)

function encodeProtoUserScore(id: bigint, name: string, score: number): Uint8Array {
  const nameBytes = new TextEncoder().encode(name);
  const out: number[] = [];

  // Field 1, wire type 0: id (varint)
  out.push(0x08);
  let v = id;
  while (v > 127n) {
    out.push(Number(v & 0x7fn) | 0x80);
    v >>= 7n;
  }
  out.push(Number(v));

  // Field 2, wire type 2: name (length-delimited)
  out.push(0x12);
  out.push(nameBytes.byteLength);
  out.push(...nameBytes);

  // Field 3, wire type 5: score (IEEE 754 float32, little-endian)
  out.push(0x1d);
  const floatBuf = new ArrayBuffer(4);
  new DataView(floatBuf).setFloat32(0, score, /* littleEndian */ true);
  out.push(...new Uint8Array(floatBuf));

  return new Uint8Array(out);
}

// --- Decode a length-delimited Protobuf UserScore message ---

function decodeProtoUserScore(bytes: Uint8Array): { id: bigint; name: string; score: number } {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let pos = 0;
  let id = 0n;
  let name = '';
  let score = 0;

  while (pos < bytes.length) {
    const tag = bytes[pos++];
    const fieldNumber = tag >> 3;
    const wireType = tag & 0x07;

    if (fieldNumber === 1 && wireType === 0) {
      // varint
      let result = 0n;
      let shift = 0n;
      while (pos < bytes.length) {
        const b = bytes[pos++];
        result |= BigInt(b & 0x7f) << shift;
        if ((b & 0x80) === 0) break;
        shift += 7n;
      }
      id = result;
    } else if (fieldNumber === 2 && wireType === 2) {
      // length-delimited string
      const len = bytes[pos++];
      name = new TextDecoder().decode(bytes.slice(pos, pos + len));
      pos += len;
    } else if (fieldNumber === 3 && wireType === 5) {
      // fixed32 float
      score = view.getFloat32(pos, true);
      pos += 4;
    } else {
      break; // unknown field, stop
    }
  }

  return { id, name, score };
}

// --- R2 streaming: serve a pre-encoded binary blob without buffering ---

async function streamFromR2(env: Env, key: string, request: Request): Promise<Response> {
  const rangeHeader = request.headers.get('Range');
  const object = await env.R2.get(key, {
    range: rangeHeader ? parseRange(rangeHeader) : undefined,
  });

  if (!object) return new Response('Not found', { status: 404 });

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('etag', object.httpEtag);
  headers.set('Accept-Ranges', 'bytes');

  // Pipe ReadableStream directly — no ArrayBuffer buffering
  return new Response(object.body, {
    status: rangeHeader ? 206 : 200,
    headers,
  });
}

function parseRange(rangeHeader: string): R2Range | undefined {
  const match = rangeHeader.match(/^bytes=(\d+)?-(\d+)?$/);
  if (!match) return undefined;
  const offset = match[1] ? parseInt(match[1], 10) : undefined;
  const end = match[2] ? parseInt(match[2], 10) : undefined;
  if (offset !== undefined && end !== undefined) return { offset, length: end - offset + 1 };
  if (offset !== undefined) return { offset };
  if (end !== undefined) return { suffix: end };
  return undefined;
}

// --- Sample dataset generator ---

function generateFeed(count: number): Array<Record<string, unknown>> {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    title: `Feed item ${i + 1}`,
    description: `A description for item ${i + 1} used in bandwidth benchmarks.`,
    score: parseFloat((Math.random() * 100).toFixed(2)),
    tags: ['mobile', 'benchmark', `tag-${i % 5}`],
    created_at: new Date(Date.now() - i * 60_000).toISOString(),
    meta: { views: i * 7, featured: i % 10 === 0 },
  }));
}

// --- Main fetch handler ---

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const format = negotiateFormat(request);

    // Feed endpoint — responds in negotiated format
    if (url.pathname === '/feed') {
      const count = Math.min(parseInt(url.searchParams.get('count') ?? '50', 10), 500);
      const feed = generateFeed(count);
      return serializeResponse({ items: feed, count }, format);
    }

    // POST — accepts JSON or MessagePack body, echoes in client's preferred format
    if (request.method === 'POST' && url.pathname === '/items') {
      const body = await deserializeBody(request) as { title: string; score: number };
      return serializeResponse(
        { id: crypto.randomUUID(), ...body, created_at: new Date().toISOString() },
        format,
        201,
      );
    }

    // Benchmark: compare payload sizes for 100 items
    if (url.pathname === '/benchmark') {
      const feed = generateFeed(100);
      const sizes = measurePayloadSizes({ items: feed });
      return Response.json({ sizes, note: `MessagePack saves ${sizes.reduction_percent} vs raw JSON` });
    }

    // Protobuf manual encoding demo
    if (url.pathname === '/proto/score') {
      const encoded = encodeProtoUserScore(12345n, 'Alice', 98.6);
      return new Response(encoded, {
        status: 200,
        headers: {
          'Content-Type': 'application/x-protobuf',
          'Content-Length': String(encoded.byteLength),
        },
      });
    }

    // Protobuf decode demo (POST raw bytes)
    if (request.method === 'POST' && url.pathname === '/proto/score/decode') {
      const buf = await request.arrayBuffer();
      const decoded = decodeProtoUserScore(new Uint8Array(buf));
      return Response.json({ id: decoded.id.toString(), name: decoded.name, score: decoded.score });
    }

    // R2 streaming: serve a pre-encoded binary dataset
    if (url.pathname.startsWith('/blobs/')) {
      const key = url.pathname.slice('/blobs/'.length);
      return streamFromR2(env, key, request);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

**Bundle size:** `@msgpack/msgpack` adds ~15 KB gzipped to the Worker bundle. Workers have a 1 MB compressed bundle limit (10 MB for Workers Paid). If bundle size is tight, a minimal MessagePack encoder covering integers, floats, strings, arrays, and maps can be implemented in ~80 lines and covers the majority of API response shapes.

**Payload size comparison (100-item feed, typical mobile API shape):**

| Format | Size | Notes |
|--------|------|-------|
| JSON (raw) | 28.4 KB | Readable; gzipped by Cloudflare automatically |
| JSON + gzip | 7.1 KB | What the mobile client actually receives |
| MessagePack (raw) | 19.2 KB | ~32% smaller than raw JSON |
| MessagePack + gzip | 6.3 KB | ~11% smaller than gzip JSON |
| Protobuf (raw) | 11.8 KB | ~58% smaller than raw JSON; requires schema |

**When binary encoding helps most:** Payloads with many repeated string keys (JSON object arrays) benefit most from MessagePack — the key names are not repeated. Payloads dominated by large string values (URLs, UUIDs) or already compressed data (images) benefit minimally.

**protobuf-es for typed schemas:** For production Protobuf usage, use `protobuf-es` (`@bufbuild/protobuf`) with generated TypeScript from `.proto` files via `buf generate`. The generated classes are plain ES modules with no Node.js dependencies and work in Workers without modification.

**ArrayBuffer in Workers:** `msgpackEncode` returns a `Uint8Array` which can be passed directly as the `Response` body. Workers serialize `Uint8Array` as binary. Do not call `.buffer` to get the underlying `ArrayBuffer` — pass the `Uint8Array` directly.

## Anti-patterns

- Using Node.js `Buffer` — Workers do not have a `Buffer` global. Use `Uint8Array` and `DataView` for all binary operations.
- Calling `await request.arrayBuffer()` for large R2 blobs — this buffers the entire object into the Worker's heap and risks exceeding the 128 MB memory limit. Pipe `object.body` (a `ReadableStream`) directly.
- Returning `application/msgpack` without a `Content-Length` header — some mobile HTTP clients cannot stream-decode MessagePack and require `Content-Length` to allocate a buffer upfront.
- Applying MessagePack to already-compressed binary payloads (images, audio, video) — binary-compressing already-compressed data reliably increases size.

## Gotchas

- Cloudflare automatically gzips `application/json` at the edge but does NOT gzip `application/msgpack` or `application/x-protobuf`. If you want compression for binary responses, set `Content-Encoding: gzip` and compress the body yourself using the `CompressionStream` API (available in Workers).
- `@msgpack/msgpack` encodes JavaScript `BigInt` as MessagePack int64 by default. If your D1 layer returns regular `number` for IDs, configure `useBigInt64: false` in the `Decoder` constructor to avoid client-side `BigInt` handling.
- The hand-rolled Protobuf encoder above only handles single-byte field lengths for the name field. For names longer than 127 bytes, encode the length as a varint (multi-byte). Use `protobuf-es` in production.
- Workers' `fetch` response body is a `ReadableStream`. When serializing with MessagePack, you must have the complete data in memory before encoding. MessagePack does not support streaming encoding in `@msgpack/msgpack`.

## Verification

```bash
# Request MessagePack feed
curl -s -H "Accept: application/msgpack" \
  "https://your-worker.workers.dev/feed?count=10" | xxd | head -5

# Compare sizes
curl -s https://your-worker.workers.dev/benchmark | jq .sizes

# POST MessagePack body (Python)
python3 -c "
import msgpack, urllib.request
body = msgpack.packb({'title': 'Test item', 'score': 42.5})
req = urllib.request.Request(
  'https://your-worker.workers.dev/items',
  data=body,
  headers={'Content-Type': 'application/msgpack', 'Accept': 'application/msgpack'}
)
print(msgpack.unpackb(urllib.request.urlopen(req).read()))
"

# Fetch Protobuf score and pipe through protoc decode
curl -s https://your-worker.workers.dev/proto/score > score.bin
protoc --decode_raw < score.bin
```

## Related

- `workers-mobile-api-versioning.md` — content-type negotiation alongside version negotiation
- `workers-r2-streaming.md` — streaming large R2 objects efficiently

## Sources

- [@msgpack/msgpack npm](https://www.npmjs.com/package/@msgpack/msgpack)
- [protobuf-es — Protobuf for ECMAScript](https://github.com/bufbuild/protobuf-es)
- [Protocol Buffers encoding guide](https://protobuf.dev/programming-guides/encoding/)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [CompressionStream in Workers](https://developers.cloudflare.com/workers/runtime-apis/web-standards/)
