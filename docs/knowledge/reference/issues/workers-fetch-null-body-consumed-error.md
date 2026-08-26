# "Body has already been consumed" Error in Cloudflare Workers Fetch API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker throws one of the following errors at runtime when reading a `Response` or `Request` body:

```
TypeError: Body has already been consumed.
TypeError: Failed to execute 'json' on 'Response': body is already used
TypeError: body used already for: https://api.example.com/data
```

Typical scenario: you read the body once to log or inspect it, then try to parse it again for your actual business logic.

```
GET /api/proxy => TypeError: Body has already been consumed.
```

This also surfaces when middleware chains pass a `Request` object through multiple handlers that each attempt to read the body.

---

## Context

- **Runtime**: Cloudflare Workers (V8 isolate)
- **API**: Fetch API — `Request`, `Response`, `Body` mixin
- **Wrangler**: 3.x
- **TypeScript**: 5.x with `@cloudflare/workers-types`
- **Pattern**: Proxy workers, middleware chains, logging decorators, A/B testing handlers

---

## Root Cause

The [WHATWG Fetch specification](https://fetch.spec.whatwg.org/#dom-body-bodyused) defines `Body` as a **single-use readable stream**. Once you call any of the body consumption methods — `.json()`, `.text()`, `.arrayBuffer()`, `.formData()`, `.blob()` — the underlying `ReadableStream` is locked and drained. The `bodyUsed` property flips to `true` permanently.

Cloudflare Workers faithfully implements this spec. Unlike Node.js `http.IncomingMessage` (which can sometimes be re-read with careful stream management), the Workers runtime gives you **no way to re-read a consumed body** — attempting to do so throws synchronously.

The spec-compliant solution is `Response.clone()` / `Request.clone()`, which creates a structural clone of the object before the body is consumed, giving you two independent streams over the same underlying bytes.

**Why clone() works**: The clone shares the underlying byte source via a tee of the `ReadableStream`. Both branches can be consumed independently, but cloning after consumption still throws — you must clone *before* any read.

---

## Broken Code

```typescript
// src/handler.ts — BROKEN
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch('https://api.example.com/data', {
      method: request.method,
      headers: request.headers,
      body: request.body,
    });

    // First read: logs the raw text for debugging
    const rawText = await upstream.text();
    console.log('[debug] upstream raw:', rawText);

    // Second read: THROWS — body already consumed above
    const data = await upstream.json(); // TypeError: Body has already been consumed

    return Response.json({ result: data });
  },
};
```

```typescript
// src/middleware.ts — BROKEN middleware chain
async function logBody(request: Request): Promise<void> {
  // Consumes the body here
  const body = await request.text();
  console.log('Request body:', body);
}

async function processRequest(request: Request, env: Env): Promise<Response> {
  await logBody(request);

  // THROWS — logBody already consumed request.body
  const payload = await request.json();
  return Response.json({ echo: payload });
}
```

```typescript
// src/ab-test.ts — BROKEN A/B split
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const bucket = Math.random() < 0.5 ? 'A' : 'B';

    // Both fetches try to forward the same request body
    const [resA, resB] = await Promise.all([
      fetch('https://origin-a.example.com', { body: request.body, method: 'POST' }),
      fetch('https://origin-b.example.com', { body: request.body, method: 'POST' }), // THROWS
    ]);

    return bucket === 'A' ? resA : resB;
  },
};
```

---

## Fix

### Option 1 — Clone the Response before any read (preferred)

```typescript
// src/handler.ts — FIXED
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch('https://api.example.com/data', {
      method: request.method,
      headers: request.headers,
      // Clone request body if you need to forward it AND read it here
      body: request.body,
    });

    // Clone BEFORE any read
    const upstreamForLog = upstream.clone();
    const upstreamForParse = upstream; // or clone() again if more reads needed

    // Each clone can be consumed independently
    const rawText = await upstreamForLog.text();
    console.log('[debug] upstream raw:', rawText);

    const data = await upstreamForParse.json();

    return Response.json({ result: data });
  },
};
```

### Option 2 — Read once, store, derive what you need

```typescript
// src/handler.ts — FIXED (single read)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch('https://api.example.com/data');

    // Read exactly once
    const rawText = await upstream.text();

    // Derive from the stored string — no second network/stream read needed
    console.log('[debug] upstream raw:', rawText);
    const data = JSON.parse(rawText) as Record<string, unknown>;

    return Response.json({ result: data });
  },
};
```

### Option 3 — Fix middleware chain with clone

```typescript
// src/middleware.ts — FIXED
async function logBody(request: Request): Promise<string> {
  // Accept a clone so caller keeps the original
  const body = await request.clone().text();
  console.log('Request body:', body);
  return body;
}

async function processRequest(request: Request, env: Env): Promise<Response> {
  await logBody(request); // operates on internal clone — original untouched

  // Original still available
  const payload = await request.json();
  return Response.json({ echo: payload });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return processRequest(request, env);
  },
};
```

### Option 4 — Fix A/B split by cloning the Request

```typescript
// src/ab-test.ts — FIXED
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const bucket = Math.random() < 0.5 ? 'A' : 'B';

    // Clone request before branching — each clone gets its own body stream
    const reqA = request.clone();
    const reqB = request.clone();

    const [resA, resB] = await Promise.all([
      fetch('https://origin-a.example.com', reqA),
      fetch('https://origin-b.example.com', reqB),
    ]);

    return bucket === 'A' ? resA : resB;
  },
};
```

---

## Verification

```bash
# 1. Run locally with wrangler dev
npx wrangler dev src/index.ts --port 8787

# 2. Send a POST with a JSON body
curl -X POST http://localhost:8787/api/proxy \
  -H 'Content-Type: application/json' \
  -d '{"hello":"world"}'
# Expected: {"result": {...}} with no TypeError in console

# 3. Check bodyUsed flag in test
npx vitest run --reporter=verbose
```

```typescript
// src/handler.test.ts
import { describe, it, expect } from 'vitest';
import { SELF } from 'cloudflare:test';

describe('fetch body consumption', () => {
  it('does not throw on double read via clone', async () => {
    const res = new Response(JSON.stringify({ ping: true }), {
      headers: { 'Content-Type': 'application/json' },
    });

    const clone = res.clone();
    expect(res.bodyUsed).toBe(false);

    const text = await clone.text();
    const json = await res.json();

    expect(text).toBe(JSON.stringify({ ping: true }));
    expect(json).toEqual({ ping: true });
    expect(res.bodyUsed).toBe(true);
  });

  it('throws when body already consumed', async () => {
    const res = new Response('hello');
    await res.text(); // consume
    await expect(res.text()).rejects.toThrow(/body/);
  });
});
```

```bash
# 4. Confirm no bodyUsed errors in wrangler tail
npx wrangler tail --format=pretty
# Filter for TypeError — should be absent after fix
```

---

## Anti-patterns

- Calling `.json()` and `.text()` on the same `Response` object in sequence without cloning.
- Passing `request.body` directly to two `fetch()` calls in a `Promise.all()`.
- Logging the body inside a shared middleware function without cloning first.
- Storing the body stream in a variable and reading it twice (streams are not arrays).
- Calling `.clone()` after the body has already been consumed — clone must happen before any read.

---

## Gotchas

- `response.clone()` is only valid while `bodyUsed === false`. Cloning a consumed response throws `TypeError: Cannot clone a disturbed ReadableStream`.
- Cloning does **not** make multiple independent network requests — it tees the already-received bytes.
- `Request.clone()` preserves all headers, method, URL, and credentials in addition to the body.
- In Durable Objects and Queue consumers, the same rule applies to `MessageBatch` event bodies.
- Workers AI binding responses (`env.AI.run(...)`) return plain JS objects, not `Response` objects — no body consumption issue there.
- `waitUntil` tasks that read a body must clone before the main handler reads it.

---

## Related

- `documentation/docs/policies/issues/workers-kv-binding-undefined-wrangler-toml.md`
- `documentation/docs/policies/issues/workers-durable-object-id-from-name-cross-script.md`
- `documentation/docs/policies/issues/workers-ai-model-not-found-gateway-error.md`

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#clone
- https://developers.cloudflare.com/workers/runtime-apis/response/#clone
- https://fetch.spec.whatwg.org/#dom-body-bodyused
- https://developers.cloudflare.com/workers/examples/alter-headers/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
