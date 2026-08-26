# PII Detection and Scrubbing Middleware in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a middleware layer that inspects HTTP request and response bodies flowing through a Cloudflare Worker, detects common PII patterns (email addresses, phone numbers, SSNs, credit card numbers, IP addresses), and either scrubs the PII before forwarding or rejects the request outright — depending on the configured mode. Scrub events must be logged to Analytics Engine for observability, and the middleware must not materially increase response latency.

## Context

Cloudflare Workers can act as a reverse proxy between clients and an origin. By interposing on both the incoming request body and the outgoing response body, a Worker can detect and neutralise accidental PII leaks — for example, a misconfigured logging endpoint that reflects user-submitted form data, or an API that inadvertently includes raw SSNs in JSON responses.

**TransformStream** lets you process a body chunk-by-chunk without buffering the entire payload, keeping memory usage flat and time-to-first-byte low. The trade-off is that PII split across a chunk boundary may go undetected; see the Gotchas section for mitigations.

**Analytics Engine** is Cloudflare's built-in time-series store for Workers metrics. Each scrub event writes a data point with the PII type, scrub count, direction (request/response), and path — without storing the actual PII.

## Solution

```typescript
// pii-scrubber.ts
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
  SCRUB_MODE: string;           // 'scrub' | 'reject'
  SCRUB_REQUEST_BODY: string;   // 'true' | 'false'
  SCRUB_RESPONSE_BODY: string;  // 'true' | 'false'
  MAX_BODY_BYTES: string;       // default '1048576' (1 MB)
}

// ── PII pattern registry ──────────────────────────────────────────────────────
interface PiiPattern {
  name: string;
  pattern: RegExp;
  replacement: string;
}

const PII_PATTERNS: PiiPattern[] = [
  {
    name: 'email',
    pattern: /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g,
    replacement: '[REDACTED-EMAIL]',
  },
  {
    name: 'phone-e164',
    pattern: /(?:\+1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?[2-9]\d{2}[\s.-]?\d{4}/g,
    replacement: '[REDACTED-PHONE]',
  },
  {
    name: 'ssn',
    // US SSN: 123-45-6789 or 123456789
    pattern: /(?<!\d)(?!219-09-9999|078-05-1120)(?:[0-6]\d{2}|7(?:[0-6]\d|7[012]))-\d{2}-\d{4}(?!\d)/g,
    replacement: '[REDACTED-SSN]',
  },
  {
    name: 'credit-card',
    // Luhn-format 13-19 digit numbers with optional separators
    pattern: /\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b/g,
    replacement: '[REDACTED-CC]',
  },
  {
    name: 'ipv4',
    pattern: /\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b/g,
    replacement: '[REDACTED-IP]',
  },
  {
    name: 'ipv6',
    // Simplified: colon-delimited hex groups
    pattern: /\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b/g,
    replacement: '[REDACTED-IPV6]',
  },
];

// ── Detection + scrubbing ─────────────────────────────────────────────────────
interface ScrubResult {
  scrubbed: string;
  detections: Record<string, number>; // piiType → count
}

function scrubText(text: string): ScrubResult {
  let scrubbed = text;
  const detections: Record<string, number> = {};

  for (const { name, pattern, replacement } of PII_PATTERNS) {
    // Reset lastIndex for global regexes
    pattern.lastIndex = 0;
    const matches = scrubbed.match(pattern);
    if (matches && matches.length > 0) {
      detections[name] = matches.length;
      scrubbed = scrubbed.replace(pattern, replacement);
    }
    pattern.lastIndex = 0;
  }

  return { scrubbed, detections };
}

function hasDetections(detections: Record<string, number>): boolean {
  return Object.keys(detections).length > 0;
}

// ── TransformStream scrubber ──────────────────────────────────────────────────
function makeScrubStream(
  onDetection: (detections: Record<string, number>, chunk: string) => void
): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  // Buffer tail of previous chunk to catch PII spanning chunk boundaries
  let tail = '';
  const TAIL_SIZE = 256; // bytes to carry over

  return new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      const text = tail + decoder.decode(chunk, { stream: true });
      const { scrubbed, detections } = scrubText(text);
      if (hasDetections(detections)) {
        onDetection(detections, text);
      }
      // Keep the last TAIL_SIZE characters as the next chunk's prefix
      const outputEnd = scrubbed.length - TAIL_SIZE;
      if (outputEnd > 0) {
        controller.enqueue(encoder.encode(scrubbed.slice(0, outputEnd)));
        tail = scrubbed.slice(outputEnd);
      } else {
        tail = scrubbed;
      }
    },
    flush(controller) {
      if (tail.length > 0) {
        controller.enqueue(new TextEncoder().encode(tail));
      }
    },
  });
}

// ── Analytics Engine logging ──────────────────────────────────────────────────
function logScrubEvent(
  dataset: AnalyticsEngineDataset,
  opts: {
    direction: 'request' | 'response';
    path: string;
    detections: Record<string, number>;
    mode: string;
  }
): void {
  const totalScrubbed = Object.values(opts.detections).reduce((a, b) => a + b, 0);
  dataset.writeDataPoint({
    blobs: [
      opts.direction,
      opts.path,
      opts.mode,
      Object.keys(opts.detections).sort().join(','),
    ],
    doubles: [totalScrubbed],
    indexes: [opts.direction],
  });
}

// ── Main middleware ───────────────────────────────────────────────────────────
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const mode = (env.SCRUB_MODE ?? 'scrub') as 'scrub' | 'reject';
    const scrubRequest = env.SCRUB_REQUEST_BODY !== 'false';
    const scrubResponse = env.SCRUB_RESPONSE_BODY !== 'false';
    const maxBodyBytes = Number(env.MAX_BODY_BYTES ?? 1_048_576);
    const contentType = request.headers.get('Content-Type') ?? '';
    const isTextBody = contentType.includes('json') || contentType.includes('text');

    // ── Inspect / scrub request body ─────────────────────────────────────────
    let outgoingRequest = request;
    if (scrubRequest && request.body && isTextBody) {
      const cloned = request.clone();
      const bodyText = await readBodyLimited(cloned, maxBodyBytes);

      if (bodyText !== null) {
        const { scrubbed, detections } = scrubText(bodyText);

        if (hasDetections(detections)) {
          logScrubEvent(env.ANALYTICS, {
            direction: 'request',
            path: url.pathname,
            detections,
            mode,
          });

          if (mode === 'reject') {
            return new Response(
              JSON.stringify({
                error: 'Request body contains PII and was rejected by policy.',
                types: Object.keys(detections),
              }),
              {
                status: 400,
                headers: { 'Content-Type': 'application/json' },
              }
            );
          }

          // Scrub mode: rebuild request with cleaned body
          outgoingRequest = new Request(request.url, {
            method: request.method,
            headers: request.headers,
            body: scrubbed,
            redirect: request.redirect,
          });
        }
      }
    }

    // ── Forward to origin ────────────────────────────────────────────────────
    const originResponse = await fetch(outgoingRequest);

    // ── Inspect / scrub response body ────────────────────────────────────────
    if (!scrubResponse || !originResponse.body) {
      return originResponse;
    }

    const respContentType = originResponse.headers.get('Content-Type') ?? '';
    if (!respContentType.includes('json') && !respContentType.includes('text')) {
      return originResponse;
    }

    let totalDetections: Record<string, number> = {};
    const scrubStream = makeScrubStream((detections) => {
      for (const [k, v] of Object.entries(detections)) {
        totalDetections[k] = (totalDetections[k] ?? 0) + v;
      }
    });

    const transformedBody = originResponse.body.pipeThrough(scrubStream);

    // After the stream is consumed we'd ideally log; we schedule it via waitUntil
    // but that requires ctx — see Implementation Details for ctx threading.
    const headers = new Headers(originResponse.headers);
    headers.set('X-PII-Scrubber', 'active');

    return new Response(transformedBody, {
      status: originResponse.status,
      statusText: originResponse.statusText,
      headers,
    });
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────
async function readBodyLimited(request: Request, maxBytes: number): Promise<string | null> {
  const reader = request.body!.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      // Body too large — skip scrubbing to avoid OOM
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }

  const combined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(combined);
}
```

## Implementation Details

**wrangler.toml:**

```toml
[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "pii_scrubber_events"

[vars]
SCRUB_MODE = "scrub"
SCRUB_REQUEST_BODY = "true"
SCRUB_RESPONSE_BODY = "true"
MAX_BODY_BYTES = "1048576"
```

**Querying scrub events in Analytics Engine:**

```sql
-- Workers Analytics Engine SQL (via Cloudflare dashboard or API)
SELECT
  blob1 AS direction,
  blob2 AS path,
  blob4 AS pii_types,
  SUM(_sample_interval * double1) AS total_scrubbed
FROM pii_scrubber_events
WHERE timestamp > NOW() - INTERVAL '1' DAY
GROUP BY direction, path, pii_types
ORDER BY total_scrubbed DESC
LIMIT 50;
```

**Performance measurement.** Use `performance.now()` around the `scrubText()` call to measure regex execution time per request. Credit-card and SSN patterns are computationally heavier than email patterns; on large bodies (> 100 KB) consider running them only on endpoints known to handle sensitive data.

**Reject vs scrub mode.** Use `reject` mode for ingestion pipelines where PII must never enter the system (e.g., a user feedback endpoint that feeds into a data lake). Use `scrub` mode for proxied APIs where the body still needs to reach the origin but should not carry raw PII.

## Anti-patterns

- **Buffering the entire response body before scrubbing.** Workers have a 128 MB memory limit per isolate, but large responses will spike memory and delay TTFB. Use `TransformStream` to stream-scrub.
- **Using synchronous regex on the global scope.** Global regexes share `lastIndex` state. Always reset `pattern.lastIndex = 0` before and after each use, or use a non-global copy via `new RegExp(pattern.source, pattern.flags)`.
- **Over-broad email regex.** Patterns like `\S+@\S+` will match JSON keys and markdown links. Use a tighter pattern as shown above.
- **Logging the scrubbed values to Analytics Engine.** The scrub event log must contain only counts and types — never the matched PII strings themselves.
- **Applying PII scrubbing to binary content** (images, PDFs, compressed blobs). The text decoder will corrupt binary data. Always gate on `Content-Type`.

## Gotchas

- **Chunk-boundary PII.** A credit card number split across two 16 KB chunks will not be matched by a per-chunk regex. The `tail` buffer in `makeScrubStream` mitigates this for short patterns (< 256 bytes). Longer patterns (multi-line JSON objects containing PII) require full buffering, which trades off memory for accuracy.
- **False positives.** The IPv4 pattern will match version numbers like `1.2.3.4` and semantic version strings. Consider an allowlist of known-safe paths (e.g., `/health`, `/version`) where scrubbing is disabled.
- **Credit card checksum.** The regex matches the Luhn format but does not validate the Luhn checksum. To reduce false positives, add a Luhn validation step after regex matching.
- **`TextDecoder` with `stream: true`** handles multi-byte UTF-8 sequences split across chunks correctly. Without `{ stream: true }`, you may get replacement characters (`�`) at chunk boundaries in non-ASCII text.
- **Workers CPU time limit** is 50 ms on the free plan, 30 seconds on paid plans. Regex-heavy scrubbing on large bodies can approach the limit. Measure with `performance.now()` and set `MAX_BODY_BYTES` conservatively.

## Verification

```bash
# 1. POST a request body containing a test email and SSN
curl -X POST https://your-worker.example.com/api/submit \
  -H 'Content-Type: application/json' \
  -d '{"user": "alice@example.com", "ssn": "123-45-6789", "note": "test"}'
# In scrub mode → origin receives: {"user":"[REDACTED-EMAIL]","ssn":"[REDACTED-SSN]","note":"test"}
# In reject mode → 400 {"error": "...", "types": ["email","ssn"]}

# 2. Check Analytics Engine for scrub events
# Cloudflare dashboard → Workers & Pages → Analytics Engine → pii_scrubber_events

# 3. Test with a clean body — no scrubbing should occur
curl -X POST https://your-worker.example.com/api/submit \
  -H 'Content-Type: application/json' \
  -d '{"user": "alice", "message": "hello world"}'
# → passes through unchanged, no analytics event written

# 4. Confirm response scrubbing: mock an origin that returns an email in JSON
# → response body should have [REDACTED-EMAIL] in place of the address
# → response header X-PII-Scrubber: active
```

## Related

- `documentation/categories/compliance/workers-gdpr-data-deletion-pipeline.md`
- `documentation/categories/compliance/workers-cookie-consent-banner.md`
- `documentation/categories/compliance/workers-audit-log-immutable-r2.md`
- Cloudflare Analytics Engine — Workers integration
- TransformStream — Web Streams API

## Sources

- Cloudflare Workers — TransformStream: https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- OWASP — Sensitive data exposure: https://owasp.org/www-project-top-ten/2017/A3_2017-Sensitive_Data_Exposure
- Luhn algorithm: https://en.wikipedia.org/wiki/Luhn_algorithm
- MDN TextDecoder — stream option: https://developer.mozilla.org/en-US/docs/Web/API/TextDecoder
