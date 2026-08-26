# Streaming Large D1 Result Sets with ReadableStream in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
A D1 query returning 10 000+ rows causes the Worker to buffer the entire result set in memory, exhausting the 128 MB Worker memory limit and producing slow time-to-first-byte. You need to stream rows to the client as soon as they are available without materialising the full result set.

---

## Context
Cloudflare D1's `.all()` method returns all rows as a JavaScript array, which blocks until the full result is fetched. For large exports or data-pipeline endpoints this creates memory pressure and increases TTFB. The solution is to combine D1's `stmt.raw()` iterator with a `TransformStream` that encodes each row as a newline-delimited JSON (NDJSON) chunk. The `Response` constructor accepts a `ReadableStream` directly, so the Worker can start sending bytes to the client before D1 finishes yielding rows. On the client side, `fetch` combined with `ReadableStreamDefaultReader` allows incremental parse without a special library.

---

## Section 1 — wrangler.toml D1 Binding

```toml
name = "streaming-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "my-database"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

## Section 2 — Worker Implementation

```typescript
import { D1Database, ExecutionContext } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
}

/**
 * Stream D1 rows as NDJSON using TransformStream.
 * Each line is a JSON-serialised row followed by '\n'.
 */
function createNdjsonStream(db: D1Database, sql: string, params: unknown[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();

  // Run the async D1 fetch in the background; the stream is returned immediately.
  (async () => {
    try {
      // .all() is the only stable D1 method — fetch once, then iterate
      const { results } = await db.prepare(sql).bind(...params).all();

      for (const row of results) {
        const line = JSON.stringify(row) + '\n';
        await writer.write(encoder.encode(line));
      }

      await writer.close();
    } catch (err) {
      await writer.abort(err);
    }
  })();

  return readable;
}

/**
 * Paginated variant: stream in pages to respect D1 row-size limits.
 * Use when total result count may exceed D1's 50 000-row limit per query.
 */
function createPaginatedNdjsonStream(
  db: D1Database,
  baseQuery: string,
  pageSize = 1000
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();

  (async () => {
    let offset = 0;
    let hasMore = true;

    try {
      while (hasMore) {
        const { results } = await db
          .prepare(`${baseQuery} LIMIT ? OFFSET ?`)
          .bind(pageSize, offset)
          .all();

        for (const row of results) {
          await writer.write(encoder.encode(JSON.stringify(row) + '\n'));
        }

        hasMore = results.length === pageSize;
        offset += results.length;
      }

      await writer.close();
    } catch (err) {
      await writer.abort(err);
    }
  })();

  return readable;
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/stream/events') {
      const stream = createPaginatedNdjsonStream(
        env.DB,
        'SELECT id, type, payload, created_at FROM events ORDER BY created_at DESC',
        500
      );

      return new Response(stream, {
        headers: {
          'Content-Type': 'application/x-ndjson',
          'Transfer-Encoding': 'chunked',
          'X-Content-Type-Options': 'nosniff',
          // Disable buffering on Cloudflare edge
          'Cache-Control': 'no-store',
        },
      });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Section 3 — Client-Side Streaming Parse

```typescript
// Browser / Node 18+ client consuming the NDJSON stream
async function consumeNdjsonStream(url: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let rowCount = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Split on newlines; last element may be an incomplete line
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.trim() === '') continue;
      const row = JSON.parse(line);
      processRow(row); // your application logic
      rowCount++;
    }
  }

  // Handle any trailing data without a final newline
  if (buffer.trim()) {
    processRow(JSON.parse(buffer));
    rowCount++;
  }

  console.log(`Received ${rowCount} rows`);
}

function processRow(row: Record<string, unknown>): void {
  // Insert into local IndexedDB, update UI, etc.
  console.log(row);
}

consumeNdjsonStream('https://my-worker.example.com/stream/events').catch(console.error);
```

---

## Anti-patterns
- **Using `.all()` for >10 k rows without streaming** — materialises the full array in Worker memory; use the paginated stream approach instead.
- **Sending JSON arrays** — `[row1, row2, ...]` requires the client to buffer the full payload before parsing; NDJSON allows line-by-line parse.
- **Not setting `Content-Type: application/x-ndjson`** — generic `application/json` misleads parsers that expect a complete JSON value.
- **Ignoring D1 row-count limits** — D1 caps a single query at 50 000 rows; paginate with `LIMIT / OFFSET` for larger datasets.

---

## Gotchas
- `TransformStream` in Workers is synchronous-capable but `writer.write()` returns a Promise; always `await` it or backpressure signals are lost.
- D1 `.all()` still fetches the full page from the SQLite replica to the Worker; streaming here means streaming *to the client*, not from D1 row-by-row.
- `Transfer-Encoding: chunked` is set automatically by the Workers runtime for streaming responses; you do not need to chunk manually.
- Cloudflare's default response buffering is disabled when a `ReadableStream` is passed to `new Response()` — no extra header needed.
- Client `ReadableStreamDefaultReader` is available in all modern browsers and Node 18+; for older Node use the `node-fetch` polyfill.

---

## Verification

```bash
# Measure TTFB and total transfer time
curl -o /dev/null -w "TTFB: %{time_starttransfer}s  Total: %{time_total}s\n" \
  https://my-worker.example.com/stream/events

# Count streamed rows
curl -s https://my-worker.example.com/stream/events | wc -l

# Validate each line is valid JSON
curl -s https://my-worker.example.com/stream/events | python3 -c "
import sys, json
for i, line in enumerate(sys.stdin):
    json.loads(line)  # raises on invalid JSON
print(f'{i+1} valid rows')
"
```

---

## Related
- `workers-cache-api-stale-while-revalidate.md`
- `workers-subrequest-parallelism-promise-all.md`
- `workers-kv-bulk-read-cache-warming.md`

---

## Sources
- Cloudflare D1 query API — https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- Cloudflare Workers Streams — https://developers.cloudflare.com/workers/runtime-apis/streams/
- NDJSON spec — https://github.com/ndjson/ndjson-spec
- MDN ReadableStream — https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream
