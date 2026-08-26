# Cloudflare Workers Response Size Limits: Mobile Streaming vs Desktop Buffering Disparity

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

The example project feed endpoint streams a large JSON payload from a Cloudflare Worker. Desktop
browsers render the feed progressively — content appears within 800 ms even on a large
response. Mobile clients (React Native fetch, iOS URLSession, Android OkHttp) receive nothing
for 3–6 seconds and then display all content at once, or they time out on responses over ~1 MB.
Some mobile clients intermittently receive a truncated response body (HTTP 200 with partial
JSON) that causes a JSON parse error, while desktop never sees this.

## Context

Cloudflare Workers have a hard **6 MB response body limit** for unstreamed (buffered) responses.
For streamed responses using `ReadableStream`, the limit is lifted — but only if the client
actually reads the stream. The problem is that mobile HTTP clients handle streaming fundamentally
differently from desktop browsers:

- **Desktop browsers** read `TransferEncoding: chunked` responses progressively, feeding chunks
  to the parser as they arrive. A Next.js `StreamingResponse` or `new Response(stream)` works
  naturally.
- **React Native's Fetch API** (Hermes JSI) buffers the entire response body before resolving
  the Promise. There is no streaming API in standard RN fetch — `response.body` exists but
  `getReader()` on it is not implemented in Hermes prior to React Native 0.73. Even in 0.73+,
  streaming requires explicit opt-in and the Android `OkHttp` layer must be configured to not
  buffer.
- **iOS `URLSession` / `NSURLSession`** used under React Native's networking module buffers by
  default up to 4 MB before delivering data events. Payloads between 4 MB and 6 MB cause an
  `NSURLErrorDataLengthExceedsMaximum` error that surfaces as a generic network error.
- **Android `OkHttp`** (the underlying client on RN Android) has a default response buffer of
  8 MB, but the React Native bridge serialises the body to a JS string, which in Hermes means
  copying through the JSI boundary — a 2 MB JSON string becomes ~4 MB of V8 heap on desktop
  but ~8 MB of JVM heap + JSI copy on Android, triggering GC pressure that stalls the UI thread.

## Section 1 — Worker Streaming Implementation

A Workers response that streams correctly for desktop must be written with awareness that mobile
clients may buffer it:

```typescript
// workers/api/feed.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { searchParams } = new URL(request.url);
    const cursor = searchParams.get('cursor') ?? '0';
    const limit = getMobileAwareLimit(request);

    // For mobile: return a bounded, fully-buffered, compact JSON response
    // For desktop/server: return a streaming NDJSON response
    const acceptsStreaming = request.headers.get('Accept') === 'application/x-ndjson';
    const isMobileClient = isMobile(request);

    if (acceptsStreaming && !isMobileClient) {
      return streamFeedResponse(env, cursor, limit);
    }
    return bufferedFeedResponse(env, cursor, limit);
  },
};

function getMobileAwareLimit(request: Request): number {
  const cfDeviceType = request.headers.get('cf-device-type');
  // Mobile connections: return fewer items per page to stay well under buffer limits
  if (cfDeviceType === 'mobile') return 20;
  if (cfDeviceType === 'tablet') return 30;
  return 50; // desktop
}

function isMobile(request: Request): boolean {
  const deviceType = request.headers.get('cf-device-type');
  if (deviceType) return deviceType === 'mobile' || deviceType === 'tablet';
  // Fallback UA sniff for clients that don't hit CF edge (e.g. Workers local dev)
  const ua = request.headers.get('user-agent') ?? '';
  return /Android|iPhone|iPad|okhttp|CFNetwork/i.test(ua);
}

async function bufferedFeedResponse(
  env: Env,
  cursor: string,
  limit: number
): Promise<Response> {
  const posts = await env.DB.prepare(
    'SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?'
  )
    .bind(limit, Number(cursor))
    .all();

  // Compact JSON — skip whitespace for mobile to reduce payload size
  const body = JSON.stringify({ posts: posts.results, nextCursor: Number(cursor) + limit });

  return new Response(body, {
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'private, max-age=30',
      'CF-Cache-Status': 'BYPASS',
    },
  });
}

async function streamFeedResponse(
  env: Env,
  cursor: string,
  limit: number
): Promise<Response> {
  const { readable, writable } = new TransformStream();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  // Fire-and-forget: stream rows as NDJSON
  (async () => {
    const stmt = env.DB.prepare(
      'SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?'
    ).bind(limit, Number(cursor));

    const results = await stmt.all();
    for (const row of results.results) {
      await writer.write(encoder.encode(JSON.stringify(row) + '\n'));
    }
    await writer.close();
  })();

  return new Response(readable, {
    headers: {
      'Content-Type': 'application/x-ndjson',
      'Transfer-Encoding': 'chunked',
      'Cache-Control': 'no-store',
    },
  });
}
```

## Section 2 — React Native Fetch: Handling Large Responses

```typescript
// src/api/feed.ts — React Native client
const MAX_SAFE_RESPONSE_BYTES = 512 * 1024; // 512 KB mobile safety limit

export async function fetchFeed(cursor: number = 0): Promise<FeedPage> {
  const url = `https://api.example.com/feed?cursor=${cursor}`;

  // React Native fetch — DO NOT request streaming; buffer the response
  // Use compact JSON (no 'Accept: application/x-ndjson')
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Accept': 'application/json',
      'X-Client-Type': 'react-native',
    },
  });

  if (!response.ok) {
    throw new Error(`Feed fetch failed: ${response.status}`);
  }

  // Check Content-Length before buffering — abort if too large
  const contentLength = response.headers.get('content-length');
  if (contentLength && parseInt(contentLength, 10) > MAX_SAFE_RESPONSE_BYTES) {
    // Server should never send this for mobile — log and request smaller page
    console.warn(`Feed response too large (${contentLength} bytes), retrying with smaller page`);
    return fetchFeed(cursor); // will get limit=20 from Worker based on UA
  }

  const data = await response.json();
  return data as FeedPage;
}
```

## Section 3 — Response Size Budget: Mobile vs Desktop

Staying within safe limits prevents truncation and GC pressure:

| Client                          | Safe response size   | Hard limit         | Notes                                      |
|---------------------------------|----------------------|--------------------|--------------------------------------------|
| Desktop browser (Chrome/FF)     | Up to 50 MB streamed | 6 MB buffered      | Streaming via ReadableStream is safe       |
| Desktop Next.js SSR fetch       | Up to 6 MB           | 6 MB Workers limit | Server-to-server, no mobile constraints    |
| iOS URLSession (RN networking)  | Up to 3.5 MB         | 4 MB (NSURLError)  | Buffer entire response in memory before JS |
| Android OkHttp (RN networking)  | Up to 2 MB           | 8 MB OkHttp buf    | JSI serialisation doubles effective cost   |
| Android WebView (Capacitor)     | Up to 4 MB           | Varies by WebView  | Subject to OS memory pressure on low-end   |
| iOS WKWebView (Capacitor)       | Up to 4 MB           | Per WKWebView docs | Performance degrades above 2 MB on iPhone X|

**Target for example project mobile API responses: < 100 KB per feed page (20 posts × ~5 KB each).**

## Section 4 — wrangler.toml and Env Configuration

```toml
# wrangler.toml — no streaming-specific config, but set limits via vars
name = "example project-api"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
MOBILE_PAGE_SIZE = "20"
DESKTOP_PAGE_SIZE = "50"
MAX_RESPONSE_BYTES = "524288"  # 512 KB ceiling for all clients

[[d1_databases]]
binding = "DB"
database_name = "example project-production"
database_id = "your-d1-database-id"
```

```typescript
// Access in Worker
const pageSize = isMobile(request)
  ? parseInt(env.MOBILE_PAGE_SIZE, 10)
  : parseInt(env.DESKTOP_PAGE_SIZE, 10);
```

## Anti-patterns

- **Streaming NDJSON to React Native clients**: RN's fetch does not consume chunks as they
  arrive — it waits for the entire stream to complete before resolving. You get no benefit from
  streaming and significant overhead from the `Transfer-Encoding: chunked` framing.
- **Returning the same payload size to all clients**: A 2 MB JSON response is fine for desktop
  but will cause GC pauses, delayed parsing, and occasional OOM crashes on low-end Android
  devices with 2 GB RAM.
- **Relying on the 6 MB Workers limit as a mobile guide**: The Workers 6 MB cap is a server
  constraint, not a mobile safety net. Mobile clients hit practical limits at 500 KB–2 MB.
- **Using `response.body.getReader()` in RN < 0.73**: The WHATWG Streams API is not available
  in Hermes before 0.73. Calling `getReader()` silently returns `undefined` or throws — the
  response will stall indefinitely if you try to read it as a stream.
- **Gzipping without checking Accept-Encoding on mobile**: Cloudflare auto-gzips responses.
  React Native on Android does NOT automatically decompress unless OkHttp is configured with
  a `GzipRequestInterceptor`. This can cause the response body to arrive as raw gzip bytes
  that `JSON.parse` then fails on.

## Gotchas

- **Cloudflare Workers `Response` from a `ReadableStream` does NOT auto-set Content-Length.**
  Mobile clients that check Content-Length before buffering will see null and buffer blindly.
  Always set Content-Length explicitly when you know the body size, or use `Content-Type: application/json`
  with a fully-buffered response.
- **The 6 MB limit applies to the Worker's *outbound* response, not the D1 query result set.**
  D1 cursors and `.all()` results can exceed 6 MB internally — but Workers silently truncate
  the HTTP response at 6 MB without returning an error to the Worker code. You will not see an
  exception; the client just receives a truncated body.
- **`cf-device-type` is absent in Cloudflare Workers local dev (`wrangler dev`).** Simulate it:
  ```bash
  # In wrangler dev, inject the header manually for testing
  curl -H 'cf-device-type: mobile' http://localhost:8787/feed
  ```
- **Cloudflare Compression Rules can interact with streaming**: If a Compression Rule applies
  `gzip` to the streaming response, it buffers the entire stream first before compressing,
  negating the streaming benefit and potentially hitting the 6 MB limit.

## Verification

```bash
# Measure response sizes by device type
# Mobile UA
curl -o /dev/null -s -w "Size: %{size_download} bytes\n" \
  -H 'User-Agent: okhttp/4.12.0' \
  https://api.example.com/feed

# Desktop UA
curl -o /dev/null -s -w "Size: %{size_download} bytes\n" \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/126' \
  https://api.example.com/feed

# Verify Content-Length is set for mobile responses
curl -sI -H 'User-Agent: okhttp/4.12.0' https://api.example.com/feed | grep -i content-length

# Simulate Workers 6 MB limit approach (dev only)
curl -s https://api.example.com/feed?limit=1000 | wc -c
```

## Related

- `mobile-network-resilience-cloudflare-workers.md`
- `cloudflare-pages-103-early-hints-mobile-desktop-disparity.md`
- `mobile-network-switching-mid-request.md`
- `react-native-cloudflare-worker-upload.md`

## Sources

- Cloudflare Workers docs: Response limits and streaming
- Cloudflare Community: "Response size exceeds 6MB limit" thread
- React Native 0.73 release notes: WHATWG Streams API availability
- OkHttp docs: BufferedSource and GzipSource behaviour
- Apple Technical Note TN3173: NSURLSession data task memory limits
- Expo SDK 50 changelog: fetch streaming improvements
