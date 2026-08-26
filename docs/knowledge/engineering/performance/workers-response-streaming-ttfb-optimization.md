# Workers Response Streaming — TTFB Optimization

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Pages served from Cloudflare Workers that run D1 queries before rendering HTML have a Time-to-First-Byte (TTFB) equal to their slowest database query. Users on high-latency connections notice a blank screen while the Worker waits for data before it can begin writing any HTML. Streaming the `<head>` and above-the-fold markup immediately while queries run in parallel cuts perceived load time significantly.

---

## Context
Cloudflare Workers supports the WHATWG Streams API — `ReadableStream`, `WritableStream`, and `TransformStream` — natively in the V8 isolate runtime. When a Worker returns a `Response` constructed from a `ReadableStream`, the runtime begins flushing bytes to the client as soon as the first `enqueue()` call is made, without waiting for the stream to close. This allows a Worker to immediately write the HTML shell (doctype, `<head>` with critical CSS, above-the-fold layout) and then pipe database results into the body once they arrive. The browser can begin parsing and applying CSS, establishing connections for fonts, and rendering the skeleton layout while the Worker is still executing the D1 query. This pattern is analogous to React 18's `renderToPipeableStream` but implemented directly in the Workers runtime without a framework.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "streaming-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]

[[d1_databases]]
binding = "DB"
database_name = "prod"
database_id = "<your-d1-database-id>"
```

## Section 2 — Implementation

```typescript
// src/index.ts
import type { Env } from './types';

/**
 * Critical CSS is inlined so the browser can render the skeleton
 * without a blocking stylesheet request.
 */
const CRITICAL_CSS = `
  *,*::before,*::after{box-sizing:border-box}
  body{margin:0;font-family:system-ui,sans-serif;background:#fff;color:#111}
  .shell{max-width:1200px;margin:0 auto;padding:0 1rem}
  .header{height:56px;display:flex;align-items:center;border-bottom:1px solid #e5e7eb}
  .skeleton{background:#f3f4f6;border-radius:4px;animation:pulse 1.5s infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
  .skeleton-text{height:1rem;margin:.5rem 0}
  .skeleton-card{height:160px;margin:1rem 0}
`;

/** Non-critical CSS is loaded asynchronously to avoid render-blocking. */
const DEFERRED_CSS_HREF = '/assets/styles.css';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const slug = url.pathname.replace('/', '') || 'home';

    // Start the D1 query immediately — do NOT await yet.
    const dbQueryPromise = env.DB.prepare(
      'SELECT id, title, body, updated_at FROM articles WHERE slug = ?1 LIMIT 1'
    )
      .bind(slug)
      .first<{ id: number; title: string; body: string; updated_at: string }>();

    // Build a ReadableStream that flushes the shell first, then the data.
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const enc = new TextEncoder();

    const write = (html: string) => writer.write(enc.encode(html));

    // Kick off the streaming pipeline without awaiting it here so we can
    // return the Response (and its ReadableStream) to the runtime immediately.
    streamPage(writer, write, enc, dbQueryPromise).catch((err) => {
      console.error('Streaming error:', err);
      writer.abort(err);
    });

    return new Response(readable, {
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        // Disable buffering on Cloudflare's edge so bytes reach the client
        // without waiting for the full response body.
        'X-Content-Type-Options': 'nosniff',
        'Transfer-Encoding': 'chunked',
        'Cache-Control': 'no-store',
      },
    });
  },
};

async function streamPage(
  writer: WritableStreamDefaultWriter,
  write: (html: string) => void,
  _enc: TextEncoder,
  dbQuery: Promise<{ id: number; title: string; body: string; updated_at: string } | null>
): Promise<void> {
  const t0 = performance.now();

  // ── 1. Flush the <head> and above-the-fold shell immediately ────────────
  write(`<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Loading…</title>
<!-- Critical CSS inlined to avoid render-blocking request -->
<style>${CRITICAL_CSS}</style>
<!-- Non-critical CSS loaded async so it never blocks first paint -->
<link rel="preload"  as="style"
      onload="this.onload=null;this.rel='stylesheet'">
<noscript><link rel="stylesheet" ></noscript>
</head><body>
<div class="shell">
  <header class="header"><strong>example.com</strong></header>
  <!-- Skeleton shown while D1 query completes -->
  <main id="content">
    <div class="skeleton skeleton-text" style="width:60%"></div>
    <div class="skeleton skeleton-card"></div>
    <div class="skeleton skeleton-text"></div>
    <div class="skeleton skeleton-text" style="width:80%"></div>
  </main>
</div>
`);

  const tShell = performance.now();
  console.log(`[stream] shell flushed in ${(tShell - t0).toFixed(1)} ms`);

  // ── 2. Await D1 result — browser is already parsing/rendering the shell ──
  const article = await dbQuery;
  const tDb = performance.now();
  console.log(`[stream] db result in ${(tDb - t0).toFixed(1)} ms (query: ${(tDb - tShell).toFixed(1)} ms)`);

  // ── 3. Stream the real content, replacing the skeleton via a script tag ──
  if (article) {
    const escaped = article.body
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    write(`
<script>
  // Replace skeleton with real content without a full re-render
  document.title = ${JSON.stringify(article.title)};
  document.getElementById('content').innerHTML =
    '<h1>${article.title.replace(/'/g, "\\'")}</h1>'
    + '<p class="updated">Updated: ${article.updated_at}</p>'
    + '<article>${escaped}</article>';
<\/script>
`);
  } else {
    write(`<script>
  document.getElementById('content').innerHTML = '<h1>Not found</h1><p>No article at this path.</p>';
  document.title = '404 — Not Found';
<\/script>
`);
  }

  // ── 4. Flush the closing tags ────────────────────────────────────────────
  write(`
<script>
  // Record navigation timing for Analytics Engine
  const ttfb = performance.getEntriesByType('navigation')[0]?.responseStart ?? 0;
  console.log('[perf] TTFB', ttfb.toFixed(1), 'ms');
<\/script>
</body></html>`);

  const tTotal = performance.now();
  console.log(`[stream] total ${(tTotal - t0).toFixed(1)} ms`);

  await writer.close();
}
```

## Section 3 — Benchmark / Verification

```typescript
// scripts/bench-ttfb.ts  (run with: npx tsx scripts/bench-ttfb.ts)
import http from 'node:http';

const TARGET = process.env.TARGET_URL ?? 'http://localhost:8787/';
const RUNS = 20;

async function measureTTFB(url: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const t0 = performance.now();
    const req = http.get(url, (res) => {
      res.once('data', () => resolve(performance.now() - t0));
      res.resume();
    });
    req.on('error', reject);
  });
}

(async () => {
  const results: number[] = [];
  for (let i = 0; i < RUNS; i++) {
    results.push(await measureTTFB(TARGET));
  }
  results.sort((a, b) => a - b);
  const p50 = results[Math.floor(RUNS * 0.5)];
  const p95 = results[Math.floor(RUNS * 0.95)];
  const avg = results.reduce((a, b) => a + b, 0) / RUNS;
  console.log(`TTFB over ${RUNS} runs:`);
  console.log(`  avg  ${avg.toFixed(1)} ms`);
  console.log(`  p50  ${p50.toFixed(1)} ms`);
  console.log(`  p95  ${p95.toFixed(1)} ms`);
})();
```

---

## Anti-patterns
- **Awaiting all queries before writing** — Defeats streaming; the browser sees no bytes until the slowest query finishes.
- **Buffering the entire response in a string** — Using `Response` with a plain string body disables chunked delivery; always pass a `ReadableStream`.
- **Forgetting `writer.close()`** — The stream hangs open; browsers display a spinner indefinitely until the connection times out.
- **Inlining all CSS** — Critical-path CSS only (above-the-fold rules, layout skeleton) should be inlined; inlining full stylesheets bloats the first chunk and wastes bandwidth on cached returns.

---

## Gotchas
- `Transfer-Encoding: chunked` is set automatically by the Workers runtime when a `ReadableStream` body is used — explicitly setting it in headers causes a duplicate-header warning in some clients.
- `performance.now()` inside a Worker measures wall-clock time since isolate start, not since the HTTP request was received; subtract the recorded start time captured at the top of the `fetch` handler.
- Cloudflare's Smart Placement feature may co-locate the Worker with the D1 primary; verify placement with `cf.colo` in the request object before assuming query latency is network-bound.
- Script tags injected via streaming are parsed and executed in order; the skeleton-replacement script must come after the closing `</main>` in the shell or `getElementById` will return `null`.

---

## Verification

```bash
# 1. Start the Worker locally
npx wrangler dev --local

# 2. Measure TTFB with curl (time_starttransfer = TTFB)
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s\nTotal: %{time_total}s\n" \
  http://localhost:8787/

# 3. Confirm chunked transfer encoding
curl -v http://localhost:8787/ 2>&1 | grep -i 'transfer-encoding'

# 4. Run the benchmark script
TARGET_URL=http://localhost:8787/ npx tsx scripts/bench-ttfb.ts
```

---

## Related
- `d1-read-replica-routing-workers.md`
- `workers-request-coalescing-durable-objects.md`

---

## Sources
- Cloudflare Workers Streaming — https://developers.cloudflare.com/workers/runtime-apis/streams/
- WHATWG Streams Standard — https://streams.spec.whatwg.org/
- web.dev TTFB Guide — https://web.dev/articles/ttfb
