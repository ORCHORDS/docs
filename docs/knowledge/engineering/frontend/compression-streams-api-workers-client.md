# Compression Streams API: Workers Compression and Client Decompression

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You want to reduce payload sizes for large JSON responses or binary blobs served from Cloudflare Workers without relying on the platform's automatic `Content-Encoding: gzip` passthrough, or you need to compress data client-side before uploading to R2. The Compression Streams API (native in both the Workers runtime and modern browsers) lets you pipe data through a `CompressionStream` or `DecompressionStream` without any external library.

## Context
The `CompressionStream` and `DecompressionStream` interfaces are part of the WHATWG Streams standard and are available natively in Cloudflare Workers, Chrome 80+, Firefox 113+, and Safari 16.4+. They support the `gzip`, `deflate`, and `deflate-raw` formats. The Workers runtime does not automatically gzip responses unless you use the platform header (`Content-Encoding: gzip`) with a pre-compressed body; the Compression Streams API gives you full control to compress on the fly, which is useful for streaming responses, batch ETL jobs, and R2 upload pipelines.

## Compressing a Response in a Worker

```typescript
// workers/compress-response.ts

async function compressBody(
  readable: ReadableStream<Uint8Array>,
  format: CompressionFormat = "gzip"
): Promise<ReadableStream<Uint8Array>> {
  const cs = new CompressionStream(format);
  readable.pipeTo(cs.writable).catch(() => {/* ignore downstream cancellation */});
  return cs.readable;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const acceptsGzip =
      request.headers.get("Accept-Encoding")?.includes("gzip") ?? false;

    // Build a large JSON payload (e.g., fetched from D1)
    const data = await env.DB.prepare("SELECT * FROM events LIMIT 1000")
      .all();
    const json = JSON.stringify(data.results);
    const encoder = new TextEncoder();
    const bytes = encoder.encode(json);

    if (!acceptsGzip) {
      return new Response(bytes, {
        headers: { "Content-Type": "application/json" },
      });
    }

    // Wrap bytes in a ReadableStream so we can pipe through CompressionStream
    const inputStream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes);
        controller.close();
      },
    });

    const compressed = await compressBody(inputStream, "gzip");

    return new Response(compressed, {
      headers: {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        "Vary": "Accept-Encoding",
      },
    });
  },
};
```

## Streaming Compression for Large Datasets

For responses too large to buffer in memory (e.g., CSV exports from D1), pipe the source stream directly through `CompressionStream`.

```typescript
// workers/stream-compress.ts
import { Env } from "./types";

export async function streamCompressedCSV(
  request: Request,
  env: Env
): Promise<Response> {
  const acceptsGzip =
    request.headers.get("Accept-Encoding")?.includes("gzip") ?? false;

  // Create a TransformStream to generate CSV rows on the fly
  const { readable, writable } = new TransformStream<string, Uint8Array>({
    transform(chunk, controller) {
      controller.enqueue(new TextEncoder().encode(chunk));
    },
  });

  // Write CSV rows asynchronously (fire-and-forget)
  const writer = writable.getWriter();
  (async () => {
    writer.write("id,name,created_at\n");
    let cursor: string | null = null;
    do {
      const stmt = cursor
        ? env.DB.prepare(
            "SELECT id, name, created_at FROM events WHERE id > ? ORDER BY id LIMIT 500"
          ).bind(cursor)
        : env.DB.prepare(
            "SELECT id, name, created_at FROM events ORDER BY id LIMIT 500"
          );
      const { results } = await stmt.all<{
        id: string;
        name: string;
        created_at: string;
      }>();
      for (const row of results) {
        writer.write(`${row.id},${JSON.stringify(row.name)},${row.created_at}\n`);
      }
      cursor = results.length === 500 ? results[results.length - 1].id : null;
    } while (cursor);
    writer.close();
  })();

  const outputStream = acceptsGzip
    ? readable.pipeThrough(new CompressionStream("gzip"))
    : readable;

  return new Response(outputStream, {
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": 'attachment; filename="events.csv"',
      ...(acceptsGzip ? { "Content-Encoding": "gzip" } : {}),
      "Vary": "Accept-Encoding",
      "Transfer-Encoding": "chunked",
    },
  });
}
```

## Client-Side Decompression in the Browser

When the browser sets `Accept-Encoding: gzip` and receives `Content-Encoding: gzip`, it decompresses transparently. However, if you need to manually decompress a gzip blob received via a raw `fetch` (e.g., from R2 with a non-standard Content-Type), use `DecompressionStream`.

```typescript
// lib/decompress.ts

export async function decompressGzip(input: Blob): Promise<string> {
  const ds = new DecompressionStream("gzip");
  const readable = input.stream().pipeThrough(ds);
  const reader = readable.getReader();
  const chunks: Uint8Array[] = [];

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    chunks.push(value);
  }

  const total = chunks.reduce((acc, c) => acc + c.byteLength, 0);
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }

  return new TextDecoder().decode(merged);
}

// Usage: fetch a pre-compressed JSON file from R2 public bucket
export async function fetchCompressedJSON<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { Accept: "application/octet-stream" },
  });
  if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);

  // R2 may serve the raw gzip bytes without Content-Encoding if the object
  // was stored with a .gz extension but an opaque Content-Type
  const blob = await res.blob();
  const text = await decompressGzip(blob);
  return JSON.parse(text) as T;
}
```

## Client-Side Compression Before R2 Upload

Compress large files in the browser before uploading to save transfer costs and R2 storage.

```typescript
// lib/compress-upload.ts

export async function compressAndUpload(
  file: File,
  presignedUrl: string,
  onProgress?: (percent: number) => void
): Promise<void> {
  const cs = new CompressionStream("gzip");
  const compressed = file.stream().pipeThrough(cs);

  // Collect to a Blob so we can set Content-Length
  const chunks: Uint8Array[] = [];
  const reader = compressed.getReader();

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    chunks.push(value);
    if (onProgress) {
      const read = chunks.reduce((a, c) => a + c.byteLength, 0);
      // Approximate progress (compressed size < original)
      onProgress(Math.min(99, Math.round((read / file.size) * 100)));
    }
  }

  const compressedBlob = new Blob(chunks, { type: "application/gzip" });

  const res = await fetch(presignedUrl, {
    method: "PUT",
    body: compressedBlob,
    headers: {
      "Content-Type": "application/gzip",
      "Content-Encoding": "identity", // Tell R2 not to re-encode
      "x-amz-meta-original-name": file.name,
      "x-amz-meta-original-size": String(file.size),
    },
  });

  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  onProgress?.(100);
}
```

## React Hook: Progress-Tracked Compressed Upload

```tsx
// hooks/useCompressedUpload.ts
import { useState, useCallback } from "react";
import { compressAndUpload } from "@/lib/compress-upload";

interface UploadState {
  progress: number;
  status: "idle" | "compressing" | "uploading" | "done" | "error";
  error?: string;
}

export function useCompressedUpload(getPresignedUrl: (name: string) => Promise<string>) {
  const [state, setState] = useState<UploadState>({
    progress: 0,
    status: "idle",
  });

  const upload = useCallback(
    async (file: File) => {
      setState({ progress: 0, status: "compressing" });
      try {
        const url = await getPresignedUrl(`${file.name}.gz`);
        setState((s) => ({ ...s, status: "uploading" }));
        await compressAndUpload(file, url, (progress) =>
          setState((s) => ({ ...s, progress }))
        );
        setState({ progress: 100, status: "done" });
      } catch (err) {
        setState({
          progress: 0,
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        });
      }
    },
    [getPresignedUrl]
  );

  return { ...state, upload };
}
```

## Anti-patterns

- **Setting `Content-Encoding: gzip` without actually compressing** — The browser will try to decompress a non-gzip body and throw a decoding error. Only set the header when the body is truly compressed.
- **Double-compressing** — If Cloudflare's automatic compression is enabled on the zone, returning a response with `Content-Encoding: gzip` you set yourself causes double compression. Use the `CF-No-Compress` response header or disable automatic compression for the route.
- **Buffering the entire compressed body before streaming** — Defeats the memory advantage of the Streams API. Pipe directly from `CompressionStream.readable` into the `Response` constructor.
- **Using `deflate` when you mean `gzip`** — `deflate` in browsers refers to raw deflate (RFC 1951), not zlib-wrapped deflate. Use `gzip` for broad compatibility.
- **Not accounting for `Vary: Accept-Encoding`** — CDN caches (including Cloudflare's) must see this header to store separate compressed and uncompressed variants.

## Gotchas

- **Workers CPU time** — Compression is CPU-intensive. Very large payloads compressed synchronously within a single Worker invocation may approach CPU limits. Prefer streaming compression or pre-compress objects at write time.
- **`Content-Length` is unknown when streaming** — Streaming a `CompressionStream` response means you cannot set `Content-Length`; the response uses chunked transfer encoding automatically.
- **Safari < 16.4** — `CompressionStream` is not available. Check `typeof CompressionStream !== "undefined"` and fall back to a WASM-based library (e.g., `fflate`) for older browsers.
- **R2 presigned PUT and `Content-Encoding`** — R2 does not modify stored objects based on `Content-Encoding`; it stores raw bytes. The header in the PUT is stored as object metadata, not interpreted. Retrieve it with `DecompressionStream` on the client side.
- **`deflate-raw` is not supported in all Workers versions** — Use `gzip` as the safe default; `deflate-raw` support was added later and may not be present in older cached Worker bundles.

## Verification

1. Deploy the `compress-response` Worker and call it with `curl -H "Accept-Encoding: gzip" --compressed` — confirm the response body decodes to valid JSON.
2. Check response headers include `Content-Encoding: gzip` and `Vary: Accept-Encoding`.
3. Without `-H "Accept-Encoding: gzip"`, confirm no `Content-Encoding` header and the body is plain JSON.
4. In the browser DevTools Network tab, upload a 5 MB file using `useCompressedUpload`; verify progress reaches 100% and the stored R2 object size is smaller than the original.
5. Run `decompressGzip(await fetch(r2Url).then(r => r.blob()))` in the console and confirm the original content is recovered.

## Related

- `cloudflare-r2-presigned-upload-frontend.md` — presigned URL generation for R2 uploads
- `wasm-cloudflare-workers-image-transform.md` — alternative WASM approach for binary processing
- `streaming-html-workers-react-rendertopipeablestream.md` — streaming response patterns in Workers
- `web-crypto-api-client-side-encryption-cloudflare-pages.md` — combining compression with encryption before upload

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Compression_Streams_API
- https://developers.cloudflare.com/workers/runtime-apis/streams/
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
