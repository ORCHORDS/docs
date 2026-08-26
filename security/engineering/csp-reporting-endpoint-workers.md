# CSP Violation Reporting Endpoint in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You have deployed a Content Security Policy but have no visibility into real-world violations. Browsers silently block resources while users encounter broken pages, and you cannot distinguish legitimate CSP violations from XSS probes. You need a durable, low-latency endpoint that collects `report-uri` and `Reporting-API` (`report-to`) payloads, deduplicates noise, rate-limits abusive senders, and writes structured records to a store you can query.

## Context

Browsers send CSP violation reports as HTTP POST requests. The legacy `report-uri` directive sends `application/csp-report` (JSON). The modern Reporting API (`report-to` directive, RFC 9218) sends `application/reports+json` (a JSON array). A Cloudflare Worker handles both formats, runs globally with sub-millisecond cold starts, and can fan out to D1 for persistent storage and Queues for async analytics without adding latency to the user's page load.

## 1. Responding to Both Report Formats

```typescript
// src/csp-report.ts
export interface CspViolation {
  documentUri: string;
  blockedUri: string;
  violatedDirective: string;
  effectiveDirective: string;
  sourceFile: string | null;
  lineNumber: number | null;
  columnNumber: number | null;
  statusCode: number | null;
  timestamp: string;
  userAgent: string;
  clientIp: string;
}

export async function parseCspReport(
  request: Request,
  clientIp: string
): Promise<CspViolation[] | null> {
  const ct = request.headers.get("content-type") ?? "";
  const ua = request.headers.get("user-agent") ?? "";
  const timestamp = new Date().toISOString();

  if (ct.includes("application/csp-report")) {
    // Legacy report-uri format
    const body = await request.json<{ "csp-report": Record<string, unknown> }>();
    const r = body["csp-report"];
    return [
      {
        documentUri: String(r["document-uri"] ?? ""),
        blockedUri: String(r["blocked-uri"] ?? ""),
        violatedDirective: String(r["violated-directive"] ?? ""),
        effectiveDirective: String(r["effective-directive"] ?? ""),
        sourceFile: r["source-file"] ? String(r["source-file"]) : null,
        lineNumber: r["line-number"] ? Number(r["line-number"]) : null,
        columnNumber: r["column-number"] ? Number(r["column-number"]) : null,
        statusCode: r["status-code"] ? Number(r["status-code"]) : null,
        timestamp,
        userAgent: ua,
        clientIp,
      },
    ];
  }

  if (ct.includes("application/reports+json")) {
    // Reporting API format – array of report objects
    const reports = await request.json<Array<Record<string, unknown>>>();
    return reports
      .filter((r) => r.type === "csp-violation")
      .map((r) => {
        const body = (r.body ?? {}) as Record<string, unknown>;
        return {
          documentUri: String(r.url ?? ""),
          blockedUri: String(body["blocked-uri"] ?? body.blockedURL ?? ""),
          violatedDirective: String(body["violated-directive"] ?? body.violatedDirective ?? ""),
          effectiveDirective: String(body["effective-directive"] ?? body.effectiveDirective ?? ""),
          sourceFile: body["source-file"] ? String(body["source-file"]) : null,
          lineNumber: body["line-number"] ? Number(body["line-number"]) : null,
          columnNumber: body["column-number"] ? Number(body["column-number"]) : null,
          statusCode: body["status-code"] ? Number(body["status-code"]) : null,
          timestamp,
          userAgent: ua,
          clientIp,
        };
      });
  }

  return null;
}
```

## 2. Rate-Limiting with Durable Objects

```typescript
// src/rate-limiter.ts
export class RateLimiter implements DurableObject {
  private readonly MAX = 60; // reports per IP per minute
  private count = 0;
  private windowStart = Date.now();

  async fetch(request: Request): Promise<Response> {
    const now = Date.now();
    if (now - this.windowStart > 60_000) {
      this.count = 0;
      this.windowStart = now;
    }
    this.count++;
    if (this.count > this.MAX) {
      return new Response("rate-limited", { status: 429 });
    }
    return new Response("ok");
  }
}
```

## 3. Persisting Violations to D1

```typescript
// src/store.ts
import { CspViolation } from "./csp-report";

export async function storeViolations(
  db: D1Database,
  violations: CspViolation[]
): Promise<void> {
  const stmt = db.prepare(
    `INSERT INTO csp_violations
       (document_uri, blocked_uri, violated_directive, effective_directive,
        source_file, line_number, column_number, status_code,
        timestamp, user_agent, client_ip)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  );

  const batch = violations.map((v) =>
    stmt.bind(
      v.documentUri, v.blockedUri, v.violatedDirective, v.effectiveDirective,
      v.sourceFile, v.lineNumber, v.columnNumber, v.statusCode,
      v.timestamp, v.userAgent, v.clientIp
    )
  );

  await db.batch(batch);
}
```

## 4. Main Worker Handler

```typescript
// src/index.ts
import { parseCspReport } from "./csp-report";
import { storeViolations } from "./store";

export { RateLimiter } from "./rate-limiter";

interface Env {
  DB: D1Database;
  RATE_LIMITER: DurableObjectNamespace;
  REPORT_QUEUE: Queue;
  ALLOWED_ORIGINS: string; // comma-separated list of origins you control
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/csp-report") {
      return new Response("Not Found", { status: 404 });
    }

    // Only accept from your own origins
    const origin = request.headers.get("origin") ?? "";
    const allowed = env.ALLOWED_ORIGINS.split(",");
    if (!allowed.includes(origin)) {
      return new Response("Forbidden", { status: 403 });
    }

    // Rate-limit per IP
    const clientIp = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const limiterStub = env.RATE_LIMITER.get(
      env.RATE_LIMITER.idFromName(clientIp)
    );
    const limitResponse = await limiterStub.fetch(request.url);
    if (limitResponse.status === 429) {
      return new Response(null, { status: 204 }); // silently drop
    }

    const violations = await parseCspReport(request, clientIp);
    if (!violations || violations.length === 0) {
      return new Response(null, { status: 204 });
    }

    // Fire-and-forget: store async
    await env.REPORT_QUEUE.send({ violations });

    return new Response(null, { status: 204 });
  },

  async queue(batch: MessageBatch<{ violations: unknown[] }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      await storeViolations(env.DB, msg.body.violations as any);
      msg.ack();
    }
  },
};
```

## 5. Sending the Headers from Your Origin Worker

```typescript
// On your main site Worker, attach both report mechanisms
const REPORT_TO = JSON.stringify([
  {
    group: "csp-endpoint",
    max_age: 86400,
    endpoints: [{ url: "https://reports.example.com/csp-report" }],
  },
]);

response.headers.set("Reporting-Endpoints", 'csp-endpoint="https://reports.example.com/csp-report"');
response.headers.set("Report-To", REPORT_TO);
response.headers.set(
  "Content-Security-Policy",
  [
    "default-src 'self'",
    "script-src 'self' 'nonce-INJECT_NONCE_HERE'",
    "report-uri https://reports.example.com/csp-report",
    "report-to csp-endpoint",
  ].join("; ")
);
```

## Anti-patterns

- **Returning 200 with a body for report endpoints.** Browsers expect 204 No Content; returning a body wastes bandwidth and can confuse some browser implementations.
- **Logging the full `blocked-uri` without sanitization.** Attacker-controlled URLs can contain data intended to pollute logs; truncate to 512 characters and strip non-printable characters.
- **No rate limiting.** A malicious page can bombard your endpoint with millions of synthetic reports; always rate-limit per IP at the Worker level.
- **Storing raw user-agent strings without length bounds.** User-Agent can be arbitrarily long; cap at 512 bytes before inserting into D1.
- **Using `report-uri` only.** `report-uri` is deprecated; implement `report-to` via the Reporting API alongside it for forward compatibility.

## Gotchas

- Browsers send CSP reports **without credentials** (no cookies); CORS preflight is not triggered, but you must still validate the `Origin` header.
- Chrome and Firefox may batch multiple reports into one `application/reports+json` body; always handle the array form.
- The `blocked-uri` for inline scripts is `"inline"`, not a URL; filter these separately in dashboards to avoid noise.
- Workers' Queues `send()` has a 128 KB message size limit; do not enqueue raw request bodies—parse first, then send structured data.
- `CF-Connecting-IP` reflects the true client IP only when your Worker is behind Cloudflare's proxying; for internal service-to-service routes, this header may be absent.

## Verification

```bash
# Trigger a synthetic CSP violation report (legacy format)
curl -X POST https://reports.example.com/csp-report \
  -H "Content-Type: application/csp-report" \
  -H "Origin: https://www.example.com" \
  -d '{"csp-report":{"document-uri":"https://www.example.com/","blocked-uri":"https://evil.com/script.js","violated-directive":"script-src","effective-directive":"script-src","status-code":200}}'
# Expect 204

# Query D1 for recent violations
wrangler d1 execute DB --command \
  "SELECT blocked_uri, COUNT(*) as hits FROM csp_violations WHERE timestamp > datetime('now','-1 hour') GROUP BY blocked_uri ORDER BY hits DESC LIMIT 20;"
```

## Related

- `content-security-policy-csp-modern-deployment.md`
- `content-security-policy-workers-nonce.md`
- `workers-tail-workers-security-event-streaming.md`
- `security-logging-what-to-log.md`
- `rate-limiting-per-user-d1-durable-objects.md`

## Sources

- W3C Content Security Policy Level 3 — https://www.w3.org/TR/CSP3/
- W3C Reporting API (RFC 9218) — https://www.w3.org/TR/reporting-1/
- Cloudflare Workers Queues — https://developers.cloudflare.com/queues/
- Cloudflare D1 batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- MDN CSP report-uri — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/report-uri
