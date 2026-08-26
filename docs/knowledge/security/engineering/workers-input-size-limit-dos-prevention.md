# Workers Input Size Limit and DoS Prevention

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers endpoint that parses JSON, reads query parameters, or processes uploaded content
is being hit with oversized payloads. Calls to `request.json()`, `request.text()`, or
`request.arrayBuffer()` block while buffering the entire body, consuming CPU time and
memory budget per-request. Under sustained attack this degrades latency for legitimate
traffic and can trigger the runtime's resource limits, surfacing 503 errors.

## Context

The Cloudflare Workers runtime enforces a hard body limit (128 MiB) but imposes no
per-endpoint application-level limit. A 50 MiB JSON payload submitted to an endpoint that
expects a 2 KB object will fully buffer before your code can reject it. Content-Length
guards let you short-circuit early; for chunked transfers you need a streaming byte-count
wrapper. Additionally, URL query strings and individual header values can be oversized to
trigger slow parsing in downstream libraries.

---

## Content-Length Guard (Fast Path)

When clients send a `Content-Length`, reject oversized requests before touching the body.
This is the cheapest possible check — it runs before any I/O.

```typescript
const LIMITS: Record<string, number> = {
  "/api/v1/items":   16 * 1024,        // 16 KiB for JSON API
  "/api/v1/upload": 10 * 1024 * 1024,  // 10 MiB for file upload
  default:            8 * 1024,        // 8 KiB fallback
};

function getBodyLimit(pathname: string): number {
  return LIMITS[pathname] ?? LIMITS.default;
}

function checkContentLength(request: Request, limit: number): Response | null {
  const cl = request.headers.get("Content-Length");
  if (cl === null) return null; // chunked — handled later

  const declared = Number(cl);
  if (!Number.isFinite(declared) || declared < 0) {
    return new Response("Invalid Content-Length", { status: 400 });
  }
  if (declared > limit) {
    return new Response(
      JSON.stringify({ error: "Payload Too Large", limit }),
      {
        status: 413,
        headers: {
          "Content-Type": "application/json",
          "Connection": "close",
        },
      },
    );
  }
  return null;
}
```

---

## Streaming Byte-Count Wrapper (Chunked Bodies)

For chunked transfer encoding there is no Content-Length. Stream the body through a
`TransformStream` that counts bytes and aborts once the limit is crossed.

```typescript
async function readBodyWithLimit(
  request: Request,
  limit: number,
): Promise<ArrayBuffer | null> {
  const chunks: Uint8Array[] = [];
  let total = 0;

  const reader = request.body?.getReader();
  if (!reader) return new ArrayBuffer(0);

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      total += value.byteLength;
      if (total > limit) {
        await reader.cancel("body too large");
        return null; // signal: over limit
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  // Concatenate chunks into a single ArrayBuffer.
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return merged.buffer;
}
```

---

## JSON Parsing with Depth and Key-Count Limits

Even a body within the byte limit can be adversarial: deeply nested JSON structures and
objects with millions of keys cause quadratic parsing work in naive parsers. After reading
the body, validate structural complexity.

```typescript
interface ParseOptions {
  maxDepth:    number;
  maxKeys:     number;
}

function measureJsonComplexity(
  value: unknown,
  opts: ParseOptions,
  depth = 0,
): { depth: number; keys: number } {
  if (depth > opts.maxDepth) {
    throw new RangeError(`JSON nesting depth exceeds ${opts.maxDepth}`);
  }

  let keys = 0;

  if (Array.isArray(value)) {
    for (const item of value) {
      const sub = measureJsonComplexity(item, opts, depth + 1);
      keys += sub.keys;
      if (keys > opts.maxKeys) throw new RangeError(`JSON key count exceeds ${opts.maxKeys}`);
    }
  } else if (value !== null && typeof value === "object") {
    const ownKeys = Object.keys(value as object);
    keys += ownKeys.length;
    if (keys > opts.maxKeys) throw new RangeError(`JSON key count exceeds ${opts.maxKeys}`);
    for (const k of ownKeys) {
      const sub = measureJsonComplexity((value as Record<string, unknown>)[k], opts, depth + 1);
      keys += sub.keys;
      if (keys > opts.maxKeys) throw new RangeError(`JSON key count exceeds ${opts.maxKeys}`);
    }
  }

  return { depth, keys };
}

function safeParseJson(
  raw: string,
  opts: ParseOptions = { maxDepth: 10, maxKeys: 500 },
): unknown {
  const parsed = JSON.parse(raw); // standard parse — throws SyntaxError on malformed
  measureJsonComplexity(parsed, opts);
  return parsed;
}
```

---

## Query String and Header Length Limits

```typescript
const MAX_QUERY_STRING_BYTES = 2048;
const MAX_SINGLE_HEADER_BYTES = 8192;

function validateRequestMetadata(request: Request): Response | null {
  const url = new URL(request.url);

  if (url.search.length > MAX_QUERY_STRING_BYTES) {
    return new Response("Query string too long", { status: 414 });
  }

  for (const [name, value] of request.headers.entries()) {
    if (value.length > MAX_SINGLE_HEADER_BYTES) {
      return new Response(`Header too long: ${name}`, { status: 431 });
    }
  }

  return null;
}
```

---

## Unified Middleware

```typescript
interface Env {}

export default {
  async fetch(request: Request, _env: Env): Promise<Response> {
    const url = new URL(request.url);

    // 1. Metadata limits.
    const metaError = validateRequestMetadata(request);
    if (metaError) return metaError;

    // 2. Content-Length fast path.
    const limit = getBodyLimit(url.pathname);
    const clError = checkContentLength(request, limit);
    if (clError) return clError;

    // 3. Streaming body read with hard cap.
    if (request.body) {
      const buf = await readBodyWithLimit(request, limit);
      if (buf === null) {
        return new Response(
          JSON.stringify({ error: "Payload Too Large", limit }),
          { status: 413, headers: { "Content-Type": "application/json" } },
        );
      }

      // 4. JSON validation.
      if (request.headers.get("Content-Type")?.includes("application/json")) {
        const text = new TextDecoder().decode(buf);
        try {
          const body = safeParseJson(text);
          return handleJson(body, request);
        } catch (err) {
          const msg = err instanceof RangeError ? err.message : "Invalid JSON";
          return new Response(JSON.stringify({ error: msg }), {
            status: 400,
            headers: { "Content-Type": "application/json" },
          });
        }
      }
    }

    return handleRequest(request);
  },
};
```

---

## Anti-patterns

- **Calling `request.json()` before any size check** — the method buffers the entire body
  then parses; an attacker can send 100 MiB before your code runs.
- **Relying solely on Content-Length** — chunked requests omit this header; attackers can
  also lie about it if your 413 check only fires after reading.
- **Returning the declared Content-Length value in error messages** — an attacker sends
  `Content-Length: 99999999999` to probe limits; echoing it leaks your thresholds.
- **No JSON depth limit** — `{"a":{"a":{"a":...}}}` with 100,000 levels causes stack
  overflow in recursive parsers.
- **Returning 500 on parse failure instead of 400** — reveals that the body was consumed
  and parsed, giving attackers an oracle for payload structure.

## Gotchas

- The Workers CPU time limit (10–30 ms on the free plan, 30 s on paid) is per-request.
  A 10 MiB JSON parse can easily exhaust the free-tier limit.
- `reader.cancel()` in the streaming wrapper may not immediately close the underlying TCP
  connection — the client may keep sending. This is fine; the Workers runtime will drain
  and discard after cancel.
- `Content-Length: 0` with a non-empty body is technically malformed but browsers send it.
  Treat `cl === "0"` as `declared === 0` and allow the body read to proceed, relying on
  the streaming cap.
- HTTP/2 has no single `Content-Length` per stream when DATA frames are used; rely on the
  streaming wrapper, not the header guard, for H2 traffic.

## Verification

```bash
# Over-limit JSON → 413
python3 -c "import json,sys; sys.stdout.write(json.dumps({'x':'A'*20000}))" | \
  curl -si -X POST https://api.example.com/api/v1/items \
  -H "Content-Type: application/json" --data-binary @- | grep HTTP

# Deep nesting → 400
python3 -c "
s = '{' * 15 + '\"k\":1' + '}' * 15
print(s)
" | curl -si -X POST https://api.example.com/api/v1/items \
  -H "Content-Type: application/json" --data-binary @- | grep -E "HTTP|error"

# Oversized query string → 414
curl -si "https://api.example.com/api/v1/items?q=$(python3 -c "print('A'*3000)")" \
  | grep HTTP
```

## Related

- `workers-multipart-form-parsing-security.md` — multipart-specific size controls
- `ddos-mitigation-strategies.md` — L3/L4 DDoS and rate limiting
- `rate-limiting-strategies.md` — request-rate controls to complement size limits
- `workers-error-response-information-disclosure.md` — safe error responses

## Sources

- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- OWASP Denial of Service Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html
- RFC 9110 §15.5.14 — 413 Content Too Large: https://www.rfc-editor.org/rfc/rfc9110#section-15.5.14
