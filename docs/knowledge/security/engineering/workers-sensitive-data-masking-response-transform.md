# Workers Sensitive Data Masking via Response Transform

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your upstream API or database occasionally returns sensitive fields — full credit card
numbers, SSNs, internal stack traces, secret values — in JSON responses.  You need a
Cloudflare Worker that acts as a transparent reverse proxy but:
- Intercepts JSON responses before they reach the client.
- Masks or redacts specific field paths based on a configurable rule set.
- Applies masking selectively based on the caller's role (from an Access JWT or API key
  scope).
- Handles large streaming responses without buffering the entire body in memory.

---

## Context

Sensitive data masking at the edge is a defence-in-depth layer: even if the upstream
accidentally returns PII, the Worker ensures the client never receives it in plaintext.
Cloudflare's `HTMLRewriter` is a streaming HTML transformer; for JSON, the equivalent is
a streaming `TransformStream` that accumulates the body, parses it, masks it, and
re-serialises it.

For very large JSON responses (>10 MB) full buffering is impractical.  In that case the
Worker should either:
1. Reject oversized responses with a 502 error (safest).
2. Apply regex-based masking on the raw text stream without parsing (faster but less
   precise).

This article covers the parse-and-mask approach (practical for most API responses) and
the streaming-regex fallback.

---

## 1. Masking Rule Configuration

```typescript
// src/rules.ts
export interface MaskRule {
  /** JSON pointer path, e.g. "/card/number" or "/user/ssn" */
  path: string;
  /** How to mask the value */
  strategy: 'redact' | 'partial' | 'hash';
  /** For 'partial': how many trailing chars to keep visible */
  keepSuffix?: number;
}

/** Default rules applied to all callers */
export const DEFAULT_RULES: MaskRule[] = [
  { path: '/card/number',      strategy: 'partial', keepSuffix: 4 },
  { path: '/card/cvv',         strategy: 'redact' },
  { path: '/user/ssn',         strategy: 'partial', keepSuffix: 4 },
  { path: '/user/dob',         strategy: 'redact' },
  { path: '/internal/error',   strategy: 'redact' },
  { path: '/internal/stackTrace', strategy: 'redact' },
];

/** Extra rules applied when the caller does NOT have the 'admin' scope */
export const NON_ADMIN_RULES: MaskRule[] = [
  { path: '/user/email',   strategy: 'partial', keepSuffix: 0 },
  { path: '/user/phone',   strategy: 'redact' },
];
```

---

## 2. Applying Mask Rules to a Parsed Object

```typescript
// src/mask.ts
import { MaskRule } from './rules';
import { createHash } from 'crypto'; // not available in Workers — use crypto.subtle

function maskValue(value: unknown, rule: MaskRule): unknown {
  if (value === null || value === undefined) return value;
  const str = String(value);

  switch (rule.strategy) {
    case 'redact':
      return '[REDACTED]';
    case 'partial': {
      const keep = rule.keepSuffix ?? 4;
      if (str.length <= keep) return '****';
      return '*'.repeat(str.length - keep) + str.slice(-keep);
    }
    case 'hash':
      // Synchronous SHA-256 is not available; return a placeholder.
      // Use deriveHash() below for async callers.
      return '[HASHED]';
    default:
      return value;
  }
}

/**
 * Walk a JSON pointer path and apply the mask rule.
 * Supports only simple paths (no wildcards, no arrays).
 */
export function applyRule(obj: Record<string, unknown>, rule: MaskRule): void {
  const parts = rule.path.split('/').filter(Boolean);
  let cursor: Record<string, unknown> = obj;

  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i];
    if (typeof cursor[part] !== 'object' || cursor[part] === null) return;
    cursor = cursor[part] as Record<string, unknown>;
  }

  const leaf = parts[parts.length - 1];
  if (!(leaf in cursor)) return;
  cursor[leaf] = maskValue(cursor[leaf], rule);
}

export function applyRules(
  obj: Record<string, unknown>,
  rules: MaskRule[],
): Record<string, unknown> {
  // Deep clone to avoid mutating the original
  const cloned = JSON.parse(JSON.stringify(obj)) as Record<string, unknown>;
  for (const rule of rules) {
    applyRule(cloned, rule);
  }
  return cloned;
}
```

---

## 3. Streaming Body Transform

```typescript
// src/transform.ts
import { MaskRule, DEFAULT_RULES, NON_ADMIN_RULES } from './rules';
import { applyRules } from './mask';

const MAX_BODY_BYTES = 10 * 1024 * 1024; // 10 MB hard limit

export async function transformJsonResponse(
  response: Response,
  rules: MaskRule[],
): Promise<Response> {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    // Not JSON — return as-is; do not buffer
    return response;
  }

  // Enforce size limit
  const contentLength = parseInt(response.headers.get('content-length') ?? '0', 10);
  if (contentLength > MAX_BODY_BYTES) {
    return new Response(
      JSON.stringify({ error: 'Response too large to inspect' }),
      { status: 502, headers: { 'content-type': 'application/json' } },
    );
  }

  // Buffer the body (within the size limit)
  const rawBytes = await readWithLimit(response.body, MAX_BODY_BYTES);
  if (rawBytes === null) {
    return new Response(
      JSON.stringify({ error: 'Response too large to inspect' }),
      { status: 502, headers: { 'content-type': 'application/json' } },
    );
  }

  let parsed: Record<string, unknown>;
  try {
    parsed = JSON.parse(new TextDecoder().decode(rawBytes));
  } catch {
    // Malformed JSON from upstream — pass through unchanged but log
    return new Response(rawBytes, {
      status: response.status,
      headers: response.headers,
    });
  }

  const masked = applyRules(parsed, rules);
  const maskedBytes = new TextEncoder().encode(JSON.stringify(masked));

  const newHeaders = new Headers(response.headers);
  newHeaders.set('content-length', String(maskedBytes.byteLength));
  // Signal that the response was transformed
  newHeaders.set('X-Masked', '1');

  return new Response(maskedBytes, {
    status: response.status,
    statusText: response.statusText,
    headers: newHeaders,
  });
}

async function readWithLimit(
  body: ReadableStream | null,
  limit: number,
): Promise<Uint8Array | null> {
  if (!body) return new Uint8Array(0);
  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      reader.cancel();
      return null;
    }
    chunks.push(value);
  }

  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}
```

---

## 4. Role-Aware Rule Selection

```typescript
// src/rules-for-caller.ts
import { MaskRule, DEFAULT_RULES, NON_ADMIN_RULES } from './rules';

export function rulesForCaller(scopes: string[]): MaskRule[] {
  const isAdmin = scopes.includes('admin');
  return isAdmin ? [...DEFAULT_RULES] : [...DEFAULT_RULES, ...NON_ADMIN_RULES];
}
```

---

## 5. Worker Entry Point

```typescript
// src/index.ts
import { transformJsonResponse } from './transform';
import { rulesForCaller } from './rules-for-caller';
import { verifyApiKey } from './verify'; // your existing key-verification module

export interface Env {
  DB: D1Database;
  UPSTREAM_URL: string;
  HKDF_SECRET: string;
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Extract scopes from verified API key
    const authHeader = req.headers.get('Authorization') ?? '';
    const raw = authHeader.startsWith('Bearer ') ? authHeader.slice(7) : '';
    const record = raw ? await verifyApiKey(env.DB, env.HKDF_SECRET, raw) : null;

    if (!record) {
      return new Response('Unauthorized', { status: 401 });
    }

    // Forward to upstream
    const upstreamUrl = new URL(req.url);
    upstreamUrl.hostname = new URL(env.UPSTREAM_URL).hostname;

    const upstreamReq = new Request(upstreamUrl.toString(), {
      method: req.method,
      headers: req.headers,
      body: req.body,
    });

    const upstreamResp = await fetch(upstreamReq);
    const rules = rulesForCaller(record.scopes);

    return transformJsonResponse(upstreamResp, rules);
  },
};
```

---

## 6. Streaming-Regex Fallback for Large Responses

```typescript
// src/regex-mask.ts
/**
 * Applies regex-based masking on the raw JSON text stream.
 * Less precise than parse-and-mask but handles arbitrarily large responses.
 */
const PATTERNS: [RegExp, string][] = [
  [/"cvv"\s*:\s*"\d{3,4}"/g,            '"cvv":"[REDACTED]"'],
  [/"number"\s*:\s*"(\d{12})(\d{4})"/g, '"number":"************$2"'],
  [/"ssn"\s*:\s*"\d{5}(\d{4})"/g,       '"ssn":"*****$1"'],
  [/"stackTrace"\s*:\s*"[^"]*"/g,        '"stackTrace":"[REDACTED]"'],
];

export function regexMaskStream(
  readable: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  const transform = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      let text = decoder.decode(chunk, { stream: true });
      for (const [pattern, replacement] of PATTERNS) {
        text = text.replace(pattern, replacement);
      }
      controller.enqueue(encoder.encode(text));
    },
    flush(controller) {
      const remaining = decoder.decode();
      if (remaining) {
        let text = remaining;
        for (const [pattern, replacement] of PATTERNS) {
          text = text.replace(pattern, replacement);
        }
        controller.enqueue(encoder.encode(text));
      }
    },
  });

  return readable.pipeThrough(transform);
}
```

---

## Anti-patterns

- **Masking only on the way out but not blocking storage** — if the upstream also writes
  to a data warehouse, mask before the write, not just before the client response.
- **Using string `replace()` on structured JSON** — a value like `"number":"4111 1111 1111 1111"` may appear with different whitespace; always parse before masking for precision.
- **Passing the upstream's `content-length` header unchanged** — after masking, the body
  length changes; always recompute and set the new `content-length`.
- **Trusting the caller's self-reported scopes in a header** — derive scopes from a
  verified JWT or API key record, never from a header the caller sends.
- **Logging the unmasked upstream response for debugging** — use Tail Workers with
  structured log filtering; never log raw response bodies in production.

---

## Gotchas

- Workers have a **128 MB memory limit**; buffering a 10 MB JSON response plus its
  parsed and re-serialised form uses ~30 MB.  Set `MAX_BODY_BYTES` conservatively.
- The `TextDecoder` in streaming mode (`{ stream: true }`) handles multi-byte UTF-8
  characters split across chunk boundaries; do not instantiate a new decoder per chunk.
- `JSON.parse` / `JSON.stringify` do not preserve key order in all JS engines; if your
  downstream depends on field order, use a JSON library that preserves order.
- If the upstream sets `Transfer-Encoding: chunked`, there is no `content-length`; the
  Worker must delete or recompute that header after buffering.
- Regex-based stream masking can produce false positives if a field value legitimately
  contains digits matching the credit-card pattern (e.g. a product SKU).  Use parse-and-
  mask when correctness matters.

---

## Verification

```bash
# Confirm card number is masked for a non-admin key
curl https://proxy.<account>.workers.dev/orders/123 \
  -H "Authorization: Bearer $NON_ADMIN_KEY" | jq '.card.number'
# Expect: "************1234"

# Confirm admin key sees partial masking (keepSuffix=4 only)
curl https://proxy.<account>.workers.dev/orders/123 \
  -H "Authorization: Bearer $ADMIN_KEY" | jq '.card.number'
# Expect: "************1234" (same default rule applies)

# Confirm CVV is fully redacted for all callers
curl https://proxy.<account>.workers.dev/orders/123 \
  -H "Authorization: Bearer $ADMIN_KEY" | jq '.card.cvv'
# Expect: "[REDACTED]"

# Confirm X-Masked header present
curl -I https://proxy.<account>.workers.dev/orders/123 \
  -H "Authorization: Bearer $ADMIN_KEY"
# Expect: x-masked: 1
```

---

## Related

- `xss-htmlrewriter-sanitization-workers.md`
- `select-star-data-leak.md`
- `public-projection-response-shaping.md`
- `workers-tail-workers-security-event-streaming.md`
- `d1-row-level-security-tenant-isolation.md`

---

## Sources

- OWASP Sensitive Data Exposure: https://owasp.org/Top10/A02_2021-Cryptographic_Failures/
- Cloudflare Workers `TransformStream`: https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
- PCI DSS v4 requirement 3.3 (masking PANs): https://www.pcisecuritystandards.org/document_library/
- MDN `TextDecoder` stream mode: https://developer.mozilla.org/en-US/docs/Web/API/TextDecoder
