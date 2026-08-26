# `TypeError: Body has already been consumed` When Reading `request.body` Twice in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker reads the incoming request body in a logging middleware, then attempts to read it again in the main business-logic handler. The second read throws `TypeError: Body has already been consumed` (or in some runtime versions `TypeError: Failed to execute 'text' on 'Body': body stream already locked`). The request body is effectively lost after the first read, causing the handler to receive an empty or null body.

---

## Context

The Fetch API specification models request and response bodies as `ReadableStream` instances. A stream can only be consumed once: once `.text()`, `.json()`, `.arrayBuffer()`, `.formData()`, or `.body.getReader()` has been called, the stream is exhausted or locked and any subsequent read attempt throws. This applies to `Request` objects in Cloudflare Workers exactly as it does in the browser. The problem surfaces most often when a logging or authentication middleware reads the body for inspection before forwarding the `Request` to the next layer of the application, but passes the *same* `Request` object rather than a clone.

---

## What Went Wrong

```typescript
// src/middleware/logger.ts — reads body without cloning
export async function logBody(request: Request): Promise<void> {
  // ❌ Consumes the stream; request.body is now closed
  const body = await request.text();
  console.log('[request body]', body);
}

// src/index.ts
import { logBody } from './middleware/logger';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    await logBody(request); // drains the body stream

    // ❌ Throws: TypeError: Body has already been consumed
    const payload = await request.json();

    return Response.json({ received: payload });
  },
};
```

Another common pattern that triggers the same error:

```typescript
// ❌ Passing the original request to a service binding after reading it
const text = await request.text();
console.log(text);
const upstreamResponse = await env.UPSTREAM.fetch(request); // body is gone
```

## Root Cause

The WHATWG `Body` mixin, implemented by both `Request` and `Response`, exposes the body as a single-use `ReadableStream`. The first call to any body-consuming method (`.text()`, `.json()`, `.arrayBuffer()`, `.formData()`, or `.body.getReader()`) locks or fully reads the stream. Subsequent calls check `body.bodyUsed` (which is now `true`) and throw.

Workers' `Request` follows this spec exactly. There is no built-in "replay" or "tee" mechanism on the `Request` object itself; consumers must opt in to multi-read patterns explicitly.

## The Fix

### Option 1 — `request.clone()` before the first read (middleware pattern)

```typescript
// src/middleware/logger.ts — fixed
export async function logBody(request: Request): Promise<void> {
  // Clone BEFORE reading. The clone gets its own independent body stream.
  const clone = request.clone();
  const body = await clone.text();
  console.log('[request body]', body);
  // Original `request` is untouched; its body stream is still open.
}

// src/index.ts
import { logBody } from './middleware/logger';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    await logBody(request); // reads a clone, original is intact

    const payload = await request.json(); // works correctly
    return Response.json({ received: payload });
  },
};
```

### Option 2 — Read once, pass the string downstream (variable reuse pattern)

```typescript
// src/index.ts — read body once and share the result
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Read body once into a string
    const rawBody = await request.text();

    // Log using the string
    console.log('[request body]', rawBody);

    // Parse using the same string — no second stream read needed
    let payload: unknown;
    try {
      payload = JSON.parse(rawBody);
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    return Response.json({ received: payload });
  },
};
```

### Option 3 — `ReadableStream.tee()` for streaming scenarios

```typescript
// For large bodies where you don't want to buffer the whole payload into a string:
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!request.body) {
      return new Response('No body', { status: 400 });
    }

    // tee() splits the stream into two independent readers
    const [streamForLog, streamForHandler] = request.body.tee();

    // Consume first copy for logging
    const logReader = streamForLog.getReader();
    const chunks: Uint8Array[] = [];
    let done = false;
    while (!done) {
      const result = await logReader.read();
      done = result.done;
      if (result.value) chunks.push(result.value);
    }
    const logText = new TextDecoder().decode(
      chunks.reduce((acc, c) => {
        const merged = new Uint8Array(acc.length + c.length);
        merged.set(acc);
        merged.set(c, acc.length);
        return merged;
      }, new Uint8Array())
    );
    console.log('[request body streaming]', logText);

    // Pass second copy to upstream
    const proxiedRequest = new Request(request.url, {
      method: request.method,
      headers: request.headers,
      body: streamForHandler,
    });

    return env.UPSTREAM.fetch(proxiedRequest);
  },
};
```

## Verification

```bash
# 1. Start wrangler dev
wrangler dev

# 2. Send a POST with a JSON body
curl -X POST http://localhost:8787/ \
  -H 'Content-Type: application/json' \
  -d '{"hello":"world"}'

# Expected response: {"received":{"hello":"world"}}
# No TypeError in wrangler dev output

# 3. Check bodyUsed flag is false before handler runs (unit test)
npx vitest run src/index.test.ts
```

```typescript
// src/index.test.ts
import { describe, it, expect } from 'vitest';

describe('body consumption', () => {
  it('request.clone() allows two reads', async () => {
    const req = new Request('http://localhost/', {
      method: 'POST',
      body: JSON.stringify({ a: 1 }),
    });

    const clone = req.clone();
    const fromClone = await clone.text();
    const fromOriginal = await req.json();

    expect(fromClone).toBe('{"a":1}');
    expect(fromOriginal).toEqual({ a: 1 });
  });

  it('reading body twice without clone throws', async () => {
    const req = new Request('http://localhost/', {
      method: 'POST',
      body: 'test',
    });

    await req.text();
    await expect(req.text()).rejects.toThrow();
  });
});
```

---

## Anti-patterns

- **Passing the original `Request` to logging middleware before reading it in the handler** — The middleware drains the stream; the handler sees an empty body. Always clone before the first read, or read once into a variable.
- **Calling `request.json()` after `request.text()`** — Even if you don't use the text result, calling `.text()` consumes the stream; the subsequent `.json()` call will throw.
- **Assuming `bodyUsed` is `false` after a failed read** — If `.json()` throws a parse error, `bodyUsed` is still `true`; the stream was consumed even though parsing failed.
- **Forwarding `request` to a `fetch()` or service binding after reading it** — The upstream receives a request with a closed body stream, which most services interpret as an empty body.

---

## Gotchas

- `request.clone()` must be called *before* any body-reading method. Calling it after `.text()` / `.json()` is too late — the cloned request will also have `bodyUsed: true`.
- Cloning a large body buffers the entire content in memory twice (original + clone). For multi-GB uploads, prefer `tee()` to keep memory usage bounded.
- `GET` and `HEAD` requests have no body by default; `request.body` will be `null`. Check for null before cloning or reading if the method is not guaranteed to be `POST`/`PUT`/`PATCH`.
- In `wrangler dev`, some error messages differ slightly from the production Workers runtime. Test with the actual error copy (`Body has already been consumed` vs `body stream already locked`) to ensure your documentation and monitoring alerts match.

---

## Related

- `workers-instanceof-error-cross-realm.md`
- `workers-crypto-randomuuid-not-available-old-compat.md`

---

## Sources

- WHATWG Fetch Spec — Body mixin — https://fetch.spec.whatwg.org/#body-mixin
- Cloudflare Workers Request docs — https://developers.cloudflare.com/workers/runtime-apis/request/
- MDN Request.clone() — https://developer.mozilla.org/en-US/docs/Web/API/Request/clone
- MDN ReadableStream.tee() — https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream/tee
