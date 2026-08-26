# Workers JSON Serialization Performance Optimization

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker that returns large JSON API responses (100 KB – 10 MB) shows high CPU time on serialization. `JSON.stringify` on complex or deeply nested objects dominates the CPU profile.

---

## Context

`JSON.stringify` in V8 is implemented in C++ and is fast for flat objects, but degrades for objects with many enumerable prototype properties, large arrays of homogeneous objects with repeated keys, and `replacer` functions called once per key.

---

## Cache Serialized Bytes in Module Scope

```typescript
const CONFIG_JSON: string = JSON.stringify({
  featureFlags: { newUI: true, betaSearch: false },
  limits: { maxUpload: 10_485_760, rateLimit: 100 },
  version: '2026-08-23',
});

export default {
  fetch(_request: Request): Response {
    return new Response(CONFIG_JSON, {
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  },
};
```

---

## Avoid Re-Serialization of Pass-Through Responses

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch('https://api.example.com/data', {
      headers: { Authorization: `Bearer ${env.API_TOKEN}` },
    });

    // Pass bytes through untouched — zero serialization cost.
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=60' },
    });
  },
};
```

---

## Streaming JSON for Large Responses

```typescript
function streamJsonArray(rows: AsyncIterable<unknown>): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      controller.enqueue(enc.encode('['));
      let first = true;
      for await (const row of rows) {
        if (!first) controller.enqueue(enc.encode(','));
        controller.enqueue(enc.encode(JSON.stringify(row)));
        first = false;
      }
      controller.enqueue(enc.encode(']'));
      controller.close();
    },
  });
}

export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    const { results } = await env.DB.prepare('SELECT id, name, score FROM leaderboard').all();
    return new Response(streamJsonArray((async function* () { yield* results; })()), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## KV-Backed Pre-Serialized JSON Cache

```typescript
export async function rebuildCache(db: D1Database, kv: KVNamespace): Promise<void> {
  const { results } = await db.prepare('SELECT * FROM summary ORDER BY rank LIMIT 1000').all();
  await kv.put('summary:v1', JSON.stringify(results), { expirationTtl: 300 });
}

export default {
  async fetch(_request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const cached = await env.KV.get('summary:v1', 'text');
    if (cached) return new Response(cached, { headers: { 'Content-Type': 'application/json' } });
    ctx.waitUntil(rebuildCache(env.DB, env.KV));
    return new Response('{"data":[]}', { headers: { 'Content-Type': 'application/json' } });
  },
};
```

---

## Anti-patterns

- **`JSON.stringify` with a `replacer` function on large arrays** — project the shape first with `map()`.
- **`structuredClone` before `JSON.stringify`** — doubles serialization work.
- **Serializing `Date` objects** — convert to Unix timestamps upstream.
- **Large `Map` or `Set` objects** — neither serializes correctly; convert first.

---

## Gotchas

- `JSON.stringify(undefined)` returns `undefined` (not a string), causing a silent empty response.
- `Response.json()` sets `charset=utf-8` automatically; manual JSON responses should include it too.

---

## Verification

```bash
wrangler dev --inspector-port 9229
# Chrome DevTools → Performance → record → look for JSON.stringify in flame chart.
```

Target: serialization of a 100 KB response under 0.5 ms CPU.

---

## Related

- `workers-json-parse-performance.md`
- `workers-module-scope-memoization.md`
- `kv-read-performance.md`

---

## Sources

- V8 Blog — Fast JSON.stringify: https://v8.dev/blog/json
- Cloudflare Workers — Response API: https://developers.cloudflare.com/workers/runtime-apis/response/
