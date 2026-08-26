# Request Smuggling Prevention with Workers Header Validation

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

HTTP request smuggling exploits disagreements between a front-end proxy and a back-end server about where one HTTP request ends and the next begins. When a Cloudflare Worker proxies to an HTTP/1.1 origin, conflicting `Content-Length` / `Transfer-Encoding` headers or CRLF-injected values in user-supplied header fields can allow an attacker to prefix a malicious request onto the next legitimate user's traffic on the origin connection.

## Context

Cloudflare's edge normalises most HTTP/1.1 smuggling vectors before they reach a Worker, but Workers that forward request headers to an origin via `fetch()` — especially those that merge user-supplied header values into the outgoing request — can re-introduce CL.TE, TE.CL, and TE.TE variants on the Worker-to-origin leg. HTTP/2-to-HTTP/1.1 downgrade on the origin side is the most common remaining attack surface. A header validation and normalisation middleware in the Worker intercepts conflicting transfer-length headers, strips hop-by-hop headers, and blocks CRLF injection before forwarding, closing the attack surface without depending on origin-side hardening.

## Transfer-Length Conflict Detector

```typescript
interface ValidationResult {
  safe: boolean;
  reason?: string;
}

function validateTransferHeaders(headers: Headers): ValidationResult {
  const cl = headers.get('Content-Length');
  const te = headers.get('Transfer-Encoding');

  // CL.TE / TE.CL: RFC 7230 §3.3.3 says if both are present, TE wins and CL
  // must be ignored — but origins may disagree. Reject rather than guess.
  if (cl !== null && te !== null) {
    return { safe: false, reason: 'CL+TE conflict: both Content-Length and Transfer-Encoding present' };
  }

  // Content-Length must be a single non-negative decimal integer
  if (cl !== null) {
    // Reject comma-delimited duplicate values ("10, 10") and non-numeric values
    if (!/^\d+$/.test(cl.trim())) {
      return { safe: false, reason: `Malformed Content-Length: "${cl}"` };
    }
  }

  // Transfer-Encoding must use only known transfer codings
  if (te !== null) {
    const codings = te.split(',').map(s => s.trim().toLowerCase());
    const known   = new Set(['chunked', 'identity']);
    const unknown = codings.filter(c => !known.has(c));

    if (unknown.length > 0) {
      // TE.TE obfuscation: "Transfer-Encoding: xchunked" or "chunked, gzip"
      return { safe: false, reason: `Unsupported Transfer-Encoding codings: ${unknown.join(', ')}` };
    }

    // RFC 7230: chunked MUST be the final transfer coding
    if (codings[codings.length - 1] !== 'chunked') {
      return { safe: false, reason: '"chunked" must be the final Transfer-Encoding coding' };
    }
  }

  return { safe: true };
}

// Detect obfuscated Transfer-Encoding values used in TE.CL desync attacks
function detectChunkedObfuscation(te: string): boolean {
  const obfuscation = [
    /chunked\x00/,          // null-byte terminator
    /[\t ]chunked/,         // leading whitespace before coding name
    /xchunked/i,            // "xchunked" unknown coding prefix
    /chunk\x65d/i,          // percent-like encoding of 'e'
  ];
  return obfuscation.some(p => p.test(te));
}
```

## Header Sanitisation — Strip Hop-by-Hop and Block CRLF Injection

```typescript
// Headers that must not be forwarded to the origin (RFC 7230 §6.1)
const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailers', 'upgrade',
]);

function sanitizeForwardedHeaders(incoming: Headers): Headers {
  const out = new Headers();

  for (const [name, value] of incoming) {
    const lc = name.toLowerCase();

    // Drop hop-by-hop headers
    if (HOP_BY_HOP.has(lc)) continue;

    // Reject header names containing non-token characters (CR, LF, NUL, colon, space)
    // These would allow HTTP header injection at the serialisation layer
    if (/[\r\n\0: ]/.test(name)) {
      console.warn(`Blocked header with illegal name characters: "${name.slice(0, 64)}"`);
      continue;
    }

    // Reject header values containing bare CR or LF — HTTP response/request splitting
    if (/[\r\n]/.test(value)) {
      console.warn(`Blocked header with CRLF in value: "${name}"`);
      continue;
    }

    // Collapse RFC 7230 obs-fold (multi-line header values) into single-line
    const clean = value.replace(/\s+/g, ' ').trim();
    out.set(name, clean);
  }

  return out;
}
```

## Proxy Worker Integrating All Checks

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Validate transfer-length headers
    const validation = validateTransferHeaders(request.headers);
    if (!validation.safe) {
      console.error('Request smuggling probe blocked', {
        ip:     request.headers.get('CF-Connecting-IP'),
        ray:    request.headers.get('CF-Ray'),
        reason: validation.reason,
      });
      return new Response('Bad Request', {
        status: 400,
        headers: { 'Content-Type': 'text/plain' },
      });
    }

    // 2. Check for TE obfuscation patterns
    const te = request.headers.get('Transfer-Encoding');
    if (te && detectChunkedObfuscation(te)) {
      return new Response('Bad Request', { status: 400 });
    }

    // 3. Sanitise and rebuild headers — never forward the original Headers object
    const forwarded = sanitizeForwardedHeaders(request.headers);

    // Re-add infrastructure headers
    const clientIp = request.headers.get('CF-Connecting-IP') ?? 'unknown';
    forwarded.set('X-Forwarded-For', clientIp);
    forwarded.set('X-Request-Id', crypto.randomUUID());
    forwarded.set('Host', new URL(env.ORIGIN_URL).host);

    // 4. Construct a clean request to the origin
    const originUrl = new URL(request.url);
    originUrl.host = new URL(env.ORIGIN_URL).host;
    originUrl.protocol = new URL(env.ORIGIN_URL).protocol;

    const proxied = new Request(originUrl.toString(), {
      method:   request.method,
      headers:  forwarded,
      body:     request.method !== 'GET' && request.method !== 'HEAD' ? request.body : null,
      redirect: 'manual', // prevent open-redirect via 3xx responses from origin
    });

    const originResponse = await fetch(proxied);

    // 5. Sanitise response headers from origin to prevent response splitting
    const responseHeaders = sanitizeForwardedHeaders(originResponse.headers);
    responseHeaders.set('X-Content-Type-Options', 'nosniff');

    return new Response(originResponse.body, {
      status:     originResponse.status,
      statusText: originResponse.statusText,
      headers:    responseHeaders,
    });
  },
};
```

## Content-Length Mismatch Detection on Origin Responses

```typescript
async function validateOriginResponse(response: Response): Promise<Response> {
  const cl = response.headers.get('Content-Length');
  if (!cl || response.body === null) return response;

  // Buffer the body and verify actual length matches declared length
  const body  = await response.arrayBuffer();
  const declared = parseInt(cl, 10);

  if (body.byteLength !== declared) {
    console.error(`Origin Content-Length mismatch: declared=${declared} actual=${body.byteLength}`);
    // Return a 502 so the client retries rather than consuming a partial body
    return new Response('Bad Gateway', { status: 502 });
  }

  return new Response(body, { status: response.status, headers: response.headers });
}
```

## Anti-patterns

- Forwarding `request.headers` directly to the origin with `new Request(url, { headers: request.headers })` — the original Headers object may contain hop-by-hop headers and user-injected CRLF values that Cloudflare's edge did not fully strip
- Constructing `new Headers()` from user-controlled key-value pairs (e.g., from a JSON body or query parameters) without name/value validation — CRLF in a header value splits the HTTP response stream at the origin
- Setting a user-supplied `Content-Length` value manually on the outgoing origin request — mismatches between the declared and actual body length are the foundation of CL.TE attacks

## Gotchas

- Workers use HTTP/2 for origin connections by default when the origin advertises ALPN h2; HTTP/2 does not use chunked encoding, so TE.CL attacks are irrelevant on HTTP/2 origin legs — but HTTP/1.1 fallback paths (plain HTTP origins, legacy servers) must still be hardened
- `new Request(url, { body: stream })` does not carry forward `Content-Length`; the Workers runtime calculates it automatically from the stream — do not copy the original `Content-Length` value from the inbound request to the outbound request object
- The `CF-Connecting-IP` header is injected by Cloudflare and should never be accepted from inbound requests if the Worker is accessed directly (e.g., on a workers.dev subdomain without a custom domain behind Cloudflare's proxy)

## Verification

```bash
# CL+TE conflict — must return 400
curl -s -X POST https://api.example.com/proxy \
  -H "Content-Length: 6" \
  -H "Transfer-Encoding: chunked" \
  -d "hello"

# CRLF injection in header value — must be stripped or return 400
curl -s https://api.example.com/proxy \
  -H $'X-Custom: value\r\nX-Injected: evil' | head -5

# Valid POST must pass through normally
curl -s -X POST https://api.example.com/proxy \
  -H "Content-Type: application/json" \
  -d '{"ok":true}'

# TE obfuscation (xchunked) — must return 400
curl -s -X POST https://api.example.com/proxy \
  -H "Transfer-Encoding: xchunked" \
  -d "0"
```

## Related

- `security/http-request-smuggling-desync.md`
- `security/crlf-injection-response-splitting.md`
- `security/ssrf-prevention-workers-fetch-allowlist.md`

## Sources

- https://portswigger.net/web-security/request-smuggling
- https://www.rfc-editor.org/rfc/rfc7230#section-3.3.3
- https://developers.cloudflare.com/workers/runtime-apis/fetch/
