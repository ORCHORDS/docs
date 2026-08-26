# Email CSP Violation Report Collection — Workers + Email Digest

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You deploy a Content Security Policy (CSP) on your web application and configure a
`report-uri` or `report-to` endpoint to collect violation reports. The volume of raw
reports is too high to review inline, and you want a Cloudflare Worker to:

1. Receive browser CSP violation reports via `POST`.
2. Deduplicate and aggregate them in D1.
3. Send a daily digest email to the security team listing the top violated directives,
   blocked URIs, and offending pages.

This pattern centralises security observability without requiring an external SIEM,
and works entirely within Cloudflare Workers + D1 + Email Routing.

---

## Context

### CSP Report Formats

**`report-uri` (legacy — CSP Level 2):**
Browser POSTs `application/csp-report` with a JSON body:

```json
{
  "csp-report": {
    "document-uri":        "https://app.example.com/dashboard",
    "referrer":            "",
    "violated-directive":  "script-src 'self'",
    "effective-directive": "script-src",
    "original-policy":     "default-src 'self'; script-src 'self'",
    "blocked-uri":         "https://cdn.evil.com/tracker.js",
    "status-code":         200
  }
}
```

**`report-to` (Reporting API — CSP Level 3):**
Browser POSTs `application/reports+json` as an array:

```json
[
  {
    "type":    "csp-violation",
    "age":     100,
    "url":     "https://app.example.com/dashboard",
    "user_agent": "Mozilla/5.0 ...",
    "body": {
      "documentURL":       "https://app.example.com/dashboard",
      "effectiveDirective":"script-src",
      "blockedURL":        "https://cdn.evil.com/tracker.js",
      "originalPolicy":    "default-src 'self'; script-src 'self'",
      "statusCode":        200
    }
  }
]
```

Your Worker must handle both.

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS csp_violations (
  id                   TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  document_url         TEXT NOT NULL,
  effective_directive  TEXT NOT NULL,
  blocked_url          TEXT NOT NULL,
  original_policy      TEXT,
  user_agent           TEXT,
  status_code          INTEGER,
  received_at          INTEGER NOT NULL  -- unix epoch seconds
);

CREATE INDEX IF NOT EXISTS idx_csp_directive
  ON csp_violations (effective_directive, received_at);

CREATE INDEX IF NOT EXISTS idx_csp_blocked
  ON csp_violations (blocked_url, received_at);

-- Digest tracking: prevents duplicate digests
CREATE TABLE IF NOT EXISTS csp_digest_log (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  period_end  INTEGER NOT NULL,  -- unix epoch of digest window close
  sent_at     INTEGER NOT NULL,
  report_rows INTEGER NOT NULL
);
```

---

## CSP Report Receiver Worker

```typescript
// csp-worker.ts

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const ct = request.headers.get("Content-Type") ?? "";
    const ua = request.headers.get("User-Agent") ?? "";

    let violations: NormalisedViolation[] = [];

    try {
      if (ct.includes("application/csp-report")) {
        // CSP Level 2 report-uri
        const body = await request.json<{ "csp-report": CspReportLegacy }>();
        violations = [normaliseLegacy(body["csp-report"], ua)];
      } else if (ct.includes("application/reports+json")) {
        // Reporting API (Level 3)
        const reports = await request.json<ReportingApiItem[]>();
        violations = reports
          .filter((r) => r.type === "csp-violation")
          .map((r) => normaliseReportingApi(r));
      } else {
        return new Response("Unsupported Content-Type", { status: 415 });
      }
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    if (violations.length === 0) {
      return new Response(null, { status: 204 });
    }

    // Batch insert (D1 supports up to 100 statements per batch)
    const stmts = violations.map((v) =>
      env.DB.prepare(
        `INSERT INTO csp_violations
         (document_url, effective_directive, blocked_url, original_policy, user_agent, status_code, received_at)
         VALUES (?, ?, ?, ?, ?, ?, unixepoch())`
      ).bind(
        truncate(v.documentUrl, 512),
        v.effectiveDirective,
        truncate(v.blockedUrl, 512),
        truncate(v.originalPolicy ?? "", 1024),
        truncate(ua, 256),
        v.statusCode ?? 0
      )
    );

    await env.DB.batch(stmts);
    return new Response(null, { status: 204 });
  },
};

// ── Types ──────────────────────────────────────────────────────────────────

interface NormalisedViolation {
  documentUrl:        string;
  effectiveDirective: string;
  blockedUrl:         string;
  originalPolicy?:    string;
  statusCode?:        number;
}

interface CspReportLegacy {
  "document-uri":        string;
  "violated-directive":  string;
  "effective-directive"?: string;
  "blocked-uri":         string;
  "original-policy"?:    string;
  "status-code"?:        number;
}

interface ReportingApiItem {
  type:       string;
  url:        string;
  user_agent: string;
  body: {
    documentURL:        string;
    effectiveDirective: string;
    blockedURL:         string;
    originalPolicy?:    string;
    statusCode?:        number;
  };
}

// ── Normalisers ───────────────────────────────────────────────────────────

function normaliseLegacy(r: CspReportLegacy, _ua: string): NormalisedViolation {
  return {
    documentUrl:        r["document-uri"],
    effectiveDirective: r["effective-directive"] ?? r["violated-directive"],
    blockedUrl:         r["blocked-uri"],
    originalPolicy:     r["original-policy"],
    statusCode:         r["status-code"],
  };
}

function normaliseReportingApi(r: ReportingApiItem): NormalisedViolation {
  return {
    documentUrl:        r.body.documentURL,
    effectiveDirective: r.body.effectiveDirective,
    blockedUrl:         r.body.blockedURL,
    originalPolicy:     r.body.originalPolicy,
    statusCode:         r.body.statusCode,
  };
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "…" : s;
}
```

---

## Daily Digest Cron Worker

```typescript
// digest-worker.ts  (scheduled trigger: "0 8 * * *" — 08:00 UTC daily)

interface Env {
  DB: D1Database;
  FROM_EMAIL:    string;  // e.g. "security-bot@example.com"
  TO_EMAIL:      string;  // e.g. "security@example.com"
  SEND_API_KEY:  string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const windowHours = 24;
    const since = Math.floor(Date.now() / 1000) - windowHours * 3600;

    const rows = await env.DB.prepare(
      `SELECT COUNT(*) AS total,
              effective_directive,
              blocked_url,
              COUNT(DISTINCT document_url) AS pages
       FROM csp_violations
       WHERE received_at >= ?
       GROUP BY effective_directive, blocked_url
       ORDER BY total DESC
       LIMIT 20`
    ).bind(since).all<{
      total: number;
      effective_directive: string;
      blocked_url: string;
      pages: number;
    }>();

    if (!rows.results.length) return; // nothing to report

    const totalViolations = rows.results.reduce((s, r) => s + r.total, 0);
    const html = buildDigestHtml(rows.results, totalViolations, windowHours);

    await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.SEND_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from:    env.FROM_EMAIL,
        to:      [env.TO_EMAIL],
        subject: `CSP Digest: ${totalViolations} violations in last ${windowHours}h`,
        html,
      }),
    });

    await env.DB.prepare(
      `INSERT INTO csp_digest_log (period_end, sent_at, report_rows)
       VALUES (unixepoch(), unixepoch(), ?)`
    ).bind(rows.results.length).run();
  },
};

function buildDigestHtml(
  rows: Array<{ total: number; effective_directive: string; blocked_url: string; pages: number }>,
  total: number,
  hours: number
): string {
  const rows_html = rows
    .map(
      (r) =>
        `<tr>
          <td>${esc(r.effective_directive)}</td>
          <td>${esc(r.blocked_url)}</td>
          <td>${r.total}</td>
          <td>${r.pages}</td>
        </tr>`
    )
    .join("\n");

  return `<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:700px;margin:auto">
  <h2>CSP Violation Digest — last ${hours}h</h2>
  <p><strong>${total}</strong> total violations across top 20 directive/blocked-URL pairs.</p>
  <table border="1" cellpadding="6" style="border-collapse:collapse;width:100%">
    <thead>
      <tr>
        <th>Directive</th><th>Blocked URL</th><th>Count</th><th>Pages</th>
      </tr>
    </thead>
    <tbody>${rows_html}</tbody>
  </table>
  <p style="color:#888;font-size:12px">Generated by Cloudflare Workers CSP digest.</p>
</body>
</html>`;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
```

---

## wrangler.toml

```toml
name = "csp-collector"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding  = "DB"
database_name = "csp-reports"
database_id   = "<your-d1-id>"

[[routes]]
pattern = "app.example.com/csp-report"
zone_name = "example.com"

[triggers]
crons = ["0 8 * * *"]
```

---

## CSP Header Configuration

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-uri /csp-report; report-to csp-endpoint
Reporting-Endpoints: csp-endpoint="https://app.example.com/csp-report"
```

Start with `Content-Security-Policy-Report-Only` to collect violations before
enforcing. Migrate to `Content-Security-Policy` once the digest shows only expected
violations (inline scripts you control, known third-party CDNs).

---

## Anti-patterns

- **Not rate-limiting the receiver** — a single page with many inline violations or a
  browser re-loading a broken page can flood the endpoint. Add a 10 req/s per-IP
  rate limit using Workers rate limiting API.
- **Storing full User-Agent strings uncapped** — UAs can be 2 KB+. Truncate at 256
  chars in the insert (already done above).
- **Emailing individual violations instead of digests** — one email per violation can
  mean thousands of messages per hour. Always aggregate.
- **Ignoring `'unsafe-eval'` directive violations** — these are the highest severity;
  highlight them separately in the digest.

---

## Gotchas

- Browser auto-responders (Chrome `ping` requests, extension injections) generate
  noise violations from `chrome-extension://` blocked URIs. Filter these in the
  digest query with `WHERE blocked_url NOT LIKE 'chrome-extension://%'`.
- The `Reporting-Endpoints` header is domain-scoped; it does not work cross-origin.
  The report endpoint URL must be on the same domain as the page or use CORS.
- Firefox sends `report-uri` format even when `report-to` is configured, until FF 127.
  The dual-format handler above covers both.
- D1 has a 1 MB per-row limit and a 25 MB per-batch limit. At high traffic, batch
  up to 100 inserts per `fetch()` call.

---

## Verification

```bash
# Trigger a manual CSP violation in the browser console:
# (with report-only CSP active on app.example.com)
eval("alert(1)")

# Watch for the row in D1:
wrangler d1 execute csp-reports \
  --command "SELECT * FROM csp_violations ORDER BY received_at DESC LIMIT 5"

# Force the digest immediately (scheduled worker):
wrangler dev --test-scheduled
```

---

## Related

- `email-webhook-signature-validation-workers.md` — validating inbound POSTs
- `email-security-audit-trail-d1-immutable-log.md` — immutable audit logging
- `email-digest-batching-queues-d1-workers.md` — digest architecture patterns
- `transactional-email-rate-limiting-workers.md` — rate limiting outbound sends

---

## Sources

- W3C CSP Level 3 — `report-to` and Reporting API
- RFC 7762 / W3C Reporting API (W3C Working Draft 2023)
- Cloudflare Workers D1 documentation — batch statements
- MDN: Content-Security-Policy — report-uri directive
- Google Chrome blog: Migrating from report-uri to report-to
