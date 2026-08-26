# Time to First Byte (TTFB) Optimisation in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Cloudflare Workers return HTML or JSON responses with high TTFB (> 200 ms)
because the Worker awaits all upstream data before writing the first byte to the
response stream. Users experience a blank page until all data is ready.

Common signals:
- Browser waterfall shows a long "Waiting (TTFB)" bar before any bytes arrive.
- RUM metrics show p75 TTFB > 300 ms on Worker-served HTML routes.
- Lighthouse "Server response times" audit fails.

---

## Context

TTFB measures the time from the client sending a request to receiving the first
byte of the response. In a Worker, TTFB is dominated by:

1. **CPU time before the first write**: KV reads, D1 queries, and upstream
   fetches that happen before `new Response()` is called.
2. **Buffering**: Constructing the full response body in memory before streaming.
3. **Geographic distance**: The Worker running far from the data it reads.

Strategies:
- **Stream `<head>` early**: Write the HTML `<head>` (fonts, critical CSS links)
  before any data fetches. The browser can start downloading sub-resources while
  the Worker fetches body data.
- **`waitUntil` for non-critical work**: Defer logging, analytics, and
  cache-fill to after the response is sent.
- **Reduce KV/D1 calls per request**: Batch, prefetch, or cache-at-edge.
- **Smart Placement**: Colocate the Worker with its primary data source.

---

## Solution

```typescript
// ttfb-optimized-worker.ts
import type { ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  KV: KVNamespace;
  ANALYTICS: AnalyticsEngineDataset;
  ASSET_BASE_URL: string; // e.g. https://assets.example.com
}

// ---------------------------------------------------------------------------
// TextEncoder helper — reused across requests (module-scope singleton)
// ---------------------------------------------------------------------------
const encoder = new TextEncoder();

function encode(s: string): Uint8Array {
  return encoder.encode(s);
}

// ---------------------------------------------------------------------------
// HTML shell — the parts we can write immediately, before any DB calls
// ---------------------------------------------------------------------------

function headHtml(title: string, assetBase: string): string {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <link rel="preload" as="style" >
  <link rel="stylesheet" >
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <script  type="module" defer></script>
</head>
<body>
<main id="root">
`;
}

function tailHtml(): string {
  return `
</main>
</body>
</html>
`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// D1 + KV batching helpers
// Combine multiple reads into as few round-trips as possible.
// ---------------------------------------------------------------------------

interface TrackRow {
  id: string;
  title: string;
  artist_name: string;
  duration_s: number;
  cover_url: string;
}

async function fetchTrackWithArtist(
  db: D1Database,
  trackId: string
): Promise<TrackRow | null> {
  // Single JOIN query instead of two sequential queries
  const result = await db
    .prepare(
      `SELECT t.id, t.title, a.name AS artist_name, t.duration_s, t.cover_url
       FROM tracks t
       JOIN artists a ON a.id = t.artist_id
       WHERE t.id = ?1
       LIMIT 1`
    )
    .bind(trackId)
    .first<TrackRow>();
  return result ?? null;
}

interface TrackMetadata {
  playCount: number;
  likeCount: number;
  tags: string[];
}

async function fetchMetadataFromKV(
  kv: KVNamespace,
  trackId: string
): Promise<TrackMetadata> {
  // Single KV read for a pre-aggregated JSON blob
  // instead of 3 separate KV reads for playCount, likeCount, tags
  const raw = await kv.get(`track:meta:${trackId}`, 'text');
  if (!raw) return { playCount: 0, likeCount: 0, tags: [] };
  try {
    return JSON.parse(raw) as TrackMetadata;
  } catch {
    return { playCount: 0, likeCount: 0, tags: [] };
  }
}

// ---------------------------------------------------------------------------
// Streaming HTML response
// Key insight: write <head> IMMEDIATELY, then await data fetches.
// The browser receives critical link tags and starts loading CSS/fonts while
// the Worker is still awaiting D1 + KV.
// ---------------------------------------------------------------------------

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const trackId = url.pathname.split('/').pop();

    if (!trackId || !/^[a-z0-9-]+$/.test(trackId)) {
      return new Response('Not found', { status: 404 });
    }

    const rumStart = performance.now();

    // Create a transform stream: we write to the writable side,
    // the readable side becomes the Response body.
    const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
    const writer = writable.getWriter();

    // ---------------------------------------------------------------------------
    // STEP 1 — Write <head> immediately (zero data dependency)
    // This is the byte that determines TTFB for the client.
    // ---------------------------------------------------------------------------
    const pageTitle = `Track — example.com`; // placeholder title before DB
    await writer.write(encode(headHtml(pageTitle, env.ASSET_BASE_URL)));

    // ---------------------------------------------------------------------------
    // STEP 2 — Fetch data in parallel while the browser is already receiving head
    // ---------------------------------------------------------------------------
    const [track, meta] = await Promise.all([
      fetchTrackWithArtist(env.DB, trackId),
      fetchMetadataFromKV(env.KV, trackId),
    ]);

    // ---------------------------------------------------------------------------
    // STEP 3 — Write body content
    // ---------------------------------------------------------------------------
    if (!track) {
      await writer.write(
        encode('<p class="error">Track not found.</p>')
      );
    } else {
      const bodyHtml = `
  <article class="track">
    <img  alt="Cover" width="300" height="300">
    <h1>${escapeHtml(track.title)}</h1>
    <p class="artist">${escapeHtml(track.artist_name)}</p>
    <p class="duration">${Math.floor(track.duration_s / 60)}:${String(track.duration_s % 60).padStart(2, '0')}</p>
    <p class="stats">${meta.playCount.toLocaleString()} plays · ${meta.likeCount.toLocaleString()} likes</p>
    <ul class="tags">${meta.tags.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>
  </article>
`;
      await writer.write(encode(bodyHtml));
    }

    // ---------------------------------------------------------------------------
    // STEP 4 — Flush closing HTML and close the stream
    // ---------------------------------------------------------------------------
    await writer.write(encode(tailHtml()));
    await writer.close();

    // ---------------------------------------------------------------------------
    // STEP 5 — Non-critical work deferred via waitUntil
    // Analytics, cache-fill, and logging run AFTER the response is sent.
    // ---------------------------------------------------------------------------
    ctx.waitUntil(
      (async () => {
        const ttfbApprox = performance.now() - rumStart;
        recordTtfb(env.ANALYTICS, request.url, ttfbApprox);

        // Optionally pre-warm related tracks
        if (track) {
          const cache = caches.default;
          const relatedUrl = `${new URL(request.url).origin}/api/related/${trackId}`;
          const existing = await cache.match(relatedUrl);
          if (!existing) {
            const related = await fetch(relatedUrl);
            if (related.ok) await cache.put(relatedUrl, related);
          }
        }
      })()
    );

    return new Response(readable, {
      status: track ? 200 : 404,
      headers: {
        'content-type': 'text/html; charset=utf-8',
        // x-content-type-options prevents MIME sniffing during streaming
        'x-content-type-options': 'nosniff',
        // No content-length when streaming (unknown final size)
        'transfer-encoding': 'chunked',
        'cache-control': track ? 'public, s-maxage=60, stale-while-revalidate=300' : 'no-store',
      },
    });
  },
};

// ---------------------------------------------------------------------------
// RUM / Analytics Engine helper
// ---------------------------------------------------------------------------

function recordTtfb(
  dataset: AnalyticsEngineDataset,
  url: string,
  ttfbMs: number
): void {
  try {
    dataset.writeDataPoint({
      blobs: [new URL(url).pathname],
      doubles: [ttfbMs],
      indexes: ['ttfb'],
    });
  } catch {
    // Non-critical
  }
}
```

---

## Implementation Details

**TransformStream as a streaming body**: `new TransformStream()` creates a
pair of `{readable, writable}`. The Worker writes bytes to `writable` while
the HTTP response carries `readable` to the client. Each `writer.write()` call
flushes a chunk immediately.

**Early `<head>` flush**: The browser starts DNS lookups, preconnects, and
stylesheet downloads as soon as it receives the first chunk. Writing even
100 bytes of HTML ahead of data fetches materially reduces the perceived loading
time, even when server TTFB (first byte) is unchanged.

**Parallel D1 + KV**: `Promise.all([fetchTrackWithArtist(...), fetchMetadataFromKV(...)])`
fires both calls simultaneously. The total wait is `max(D1 latency, KV latency)`
instead of their sum.

**Single JOIN query**: One `JOIN` in D1 replaces two sequential queries
(`SELECT * FROM tracks` then `SELECT * FROM artists`). This halves D1 round-trips.

**`waitUntil` for non-critical work**: Analytics writes and cache fills happen
after the response stream closes. The user never waits for them.

**Smart Placement** (`[placement] mode = "smart"` in `wrangler.toml`): Cloudflare
automatically routes the Worker invocation to the data centre closest to its
D1 and KV data. For D1 this can reduce round-trip latency by 30–120 ms.

---

## Anti-patterns

- **Await all data before writing**: `const body = buildHtml(await allData()); return new Response(body)`
  buffers the entire response — the client waits for the last byte of data
  before receiving the first byte of HTML.
- **Multiple sequential KV reads**: `await kv.get('a'); await kv.get('b'); await kv.get('c')`
  is three round-trips. Store pre-aggregated blobs or use `getWithMetadata` to
  combine reads.
- **Mixing `waitUntil` with stream writes**: After `writer.close()` the
  stream is done; don't attempt further writes inside `waitUntil`.
- **Missing `x-content-type-options: nosniff`**: Without it, some browsers
  MIME-sniff the streaming chunks and may pause rendering.

---

## Gotchas

- `transfer-encoding: chunked` is set automatically by the Workers runtime when
  the response body is a `ReadableStream` with no `content-length`. You do not
  need to set it manually — but explicitly setting it causes no harm.
- If the D1 query or KV read throws, `writer.close()` may never be called,
  leaving the client waiting. Always wrap the body-writing block in try/finally
  and call `writer.abort(err)` in the catch path.
- `performance.now()` inside a Worker measures wall-clock time since the
  isolate's epoch, not the request epoch. Use it for delta measurements only.
- Smart Placement is opt-in per Worker via `wrangler.toml`; it may route the
  Worker farther from the user if the data centre nearest to the DB is
  geographically distant from the requester.

---

## Verification

```bash
# Measure TTFB with curl's time_starttransfer
curl -o /dev/null -s -w 'TTFB: %{time_starttransfer}s\n' \
  https://example.com/tracks/some-track-id

# Confirm streaming (chunks arrive before body is complete)
curl -N https://example.com/tracks/some-track-id 2>&1 | head -20

# Analytics Engine GraphQL — avg TTFB over last hour
# SELECT avg(doubles[0]) FROM ANALYTICS WHERE indexes[0] = 'ttfb'
```

---

## Related

- `early-hints-103-preload.md` — 103 Early Hints for sub-resource preloading
- `workers-connection-coalescing.md` — Parallel fetches to reduce upstream RTT
- `kv-bulk-prefetch-pattern.md` — Prefetching KV data to eliminate per-request reads
- `workers-cache-warming-strategy.md` — Pre-warming responses to serve from edge

---

## Sources

- [Cloudflare Workers — Streaming responses](https://developers.cloudflare.com/workers/examples/streaming-responses/)
- [TransformStream — WHATWG Streams spec](https://streams.spec.whatwg.org/#transform-stream)
- [D1 — prepared statements](https://developers.cloudflare.com/d1/platform/client-api/)
- [Smart Placement](https://developers.cloudflare.com/workers/configuration/smart-placement/)
- [Web Vitals — TTFB](https://web.dev/ttfb/)
