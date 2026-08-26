# CSP Violation Reporting Endpoint with D1 in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You have deployed `Content-Security-Policy-Report-Only` headers on your site and want to capture violation reports in a durable store for analysis. A Cloudflare Worker serves as the `report-to` endpoint, writes deduplicated reports to D1, and a daily Cron aggregates the top violations into a Slack digest.

---

## Context
Browsers POST CSP violation reports as JSON (`application/csp-report` for legacy `report-uri`, or `application/reports+json` for the newer `Report-To` / Reporting API). The Worker parses both formats, normalises the fields, and inserts into D1 with an upsert that deduplicates on `(document_uri, blocked_uri, violated_directive)` — only the `count` and `last_seen_at` are updated for duplicate violations. A scheduled Cron runs at 09:00 UTC daily, queries top violations from the previous 24 hours, and posts a summary to Slack.

---

## D1 Schema
```sql
CREATE TABLE IF NOT EXISTS csp_violations (
  id                  TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  document_uri        TEXT NOT NULL,
  blocked_uri         TEXT NOT NULL,
  violated_directive  TEXT NOT NULL,
  effective_directive TEXT,
  original_policy     TEXT,
  source_file         TEXT,
  line_number         INTEGER,
  column_number       INTEGER,
  referrer            TEXT,
  disposition         TEXT CHECK(disposition IN ('enforce','report')) DEFAULT 'report',
  count               INTEGER NOT NULL DEFAULT 1,
  first_seen_at       INTEGER NOT NULL DEFAULT (unixepoch()),
  last_seen_at        INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_csp_dedup
  ON csp_violations(document_uri, blocked_uri, violated_directive);

CREATE INDEX IF NOT EXISTS idx_csp_last_seen ON csp_violations(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_csp_directive ON csp_violations(violated_directive);
```

---

## Report Parsing
```typescript
// src/parse-csp.ts

export interface NormalizedViolation {
  document_uri:        string;
  blocked_uri:         string;
  violated_directive:  string;
  effective_directive: string | null;
  original_policy:     string | null;
  source_file:         string | null;
  line_number:         number | null;
  column_number:       number | null;
  referrer:            string | null;
  disposition:         'enforce' | 'report';
}

/** Parse legacy application/csp-report format */
function parseCspReport(body: Record<string, unknown>): NormalizedViolation | null {
  const report = body['csp-report'] as Record<string, unknown> | undefined;
  if (!report) return null;
  return {
    document_uri:        String(report['document-uri'] ?? ''),
    blocked_uri:         String(report['blocked-uri'] ?? ''),
    violated_directive:  String(report['violated-directive'] ?? ''),
    effective_directive: report['effective-directive'] ? String(report['effective-directive']) : null,
    original_policy:     report['original-policy'] ? String(report['original-policy']) : null,
    source_file:         report['source-file'] ? String(report['source-file']) : null,
    line_number:         report['line-number'] != null ? Number(report['line-number']) : null,
    column_number:       report['column-number'] != null ? Number(report['column-number']) : null,
    referrer:            report['referrer'] ? String(report['referrer']) : null,
    disposition:         report['disposition'] === 'enforce' ? 'enforce' : 'report',
  };
}

/** Parse newer application/reports+json format (array of reports) */
function parseReportingApi(body: unknown[]): NormalizedViolation[] {
  const results: NormalizedViolation[] = [];
  for (const item of body) {
    const r = item as Record<string, unknown>;
    if (r['type'] !== 'csp-violation') continue;
    const body_ = r['body'] as Record<string, unknown> | undefined;
    if (!body_) continue;
    results.push({
      document_uri:        String(r['url'] ?? ''),
      blocked_uri:         String(body_['blockedURL'] ?? ''),
      violated_directive:  String(body_['violatedDirective'] ?? ''),
      effective_directive: body_['effectiveDirective'] ? String(body_['effectiveDirective']) : null,
      original_policy:     body_['originalPolicy'] ? String(body_['originalPolicy']) : null,
      source_file:         body_['sourceFile'] ? String(body_['sourceFile']) : null,
      line_number:         body_['lineNumber'] != null ? Number(body_['lineNumber']) : null,
      column_number:       body_['columnNumber'] != null ? Number(body_['columnNumber']) : null,
      referrer:            r['referrer'] ? String(r['referrer']) : null,
      disposition:         body_['disposition'] === 'enforce' ? 'enforce' : 'report',
    });
  }
  return results;
}

export async function parseViolations(
  request: Request
): Promise<NormalizedViolation[]> {
  const ct = request.headers.get('Content-Type') ?? '';

  if (ct.includes('application/reports+json')) {
    const arr = await request.json<unknown[]>();
    return parseReportingApi(Array.isArray(arr) ? arr : []);
  }

  // Legacy application/csp-report or application/json
  const obj = await request.json<Record<string, unknown>>();
  const v = parseCspReport(obj);
  return v ? [v] : [];
}
```

---

## Worker: Report Ingestion + Cron Aggregation
```typescript
// src/index.ts
import type { Env } from './env';
import { parseViolations } from './parse-csp';

async function ingestViolations(request: Request, env: Env): Promise<Response> {
  let violations;
  try {
    violations = await parseViolations(request);
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  if (violations.length === 0) {
    return new Response('No violations parsed', { status: 204 });
  }

  const now = Math.floor(Date.now() / 1000);

  // Batch upsert with dedup
  const stmt = env.DB.prepare(
    `INSERT INTO csp_violations
       (document_uri, blocked_uri, violated_directive, effective_directive,
        original_policy, source_file, line_number, column_number,
        referrer, disposition, first_seen_at, last_seen_at, count)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
     ON CONFLICT(document_uri, blocked_uri, violated_directive)
     DO UPDATE SET count = count + 1, last_seen_at = excluded.last_seen_at`
  );

  const batch = violations.map(v =>
    stmt.bind(
      v.document_uri, v.blocked_uri, v.violated_directive,
      v.effective_directive, v.original_policy, v.source_file,
      v.line_number, v.column_number, v.referrer, v.disposition,
      now, now
    )
  );

  await env.DB.batch(batch);
  return new Response(null, { status: 204 });
}

async function postToSlack(webhookUrl: string, text: string): Promise<void> {
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
}

async function runDailyDigest(env: Env): Promise<void> {
  const since = Math.floor(Date.now() / 1000) - 86400;

  const rows = await env.DB.prepare(
    `SELECT violated_directive, blocked_uri, SUM(count) as total
     FROM csp_violations
     WHERE last_seen_at > ?
     GROUP BY violated_directive, blocked_uri
     ORDER BY total DESC
     LIMIT 10`
  ).bind(since).all<{ violated_directive: string; blocked_uri: string; total: number }>();

  if (rows.results.length === 0) {
    await postToSlack(env.SLACK_WEBHOOK_URL, ':white_check_mark: No CSP violations in the last 24 hours.');
    return;
  }

  const lines = rows.results.map(
    (r, i) => `${i + 1}. \`${r.violated_directive}\` blocked \`${r.blocked_uri}\` — ${r.total}x`
  );

  const message = [
    '*CSP Violation Digest (last 24 hours) :shield:*',
    ...lines,
  ].join('\n');

  await postToSlack(env.SLACK_WEBHOOK_URL, message);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/csp-report') {
      return ingestViolations(request, env);
    }

    return new Response('Not Found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runDailyDigest(env));
  },
};
```

---

## wrangler.toml
```toml
[triggers]
crons = ["0 9 * * *"]  # 09:00 UTC daily

[[d1_databases]]
binding      = "DB"
database_name = "my-db"
database_id   = "<D1_DATABASE_ID>"
```

```bash
wrangler secret put SLACK_WEBHOOK_URL
```

## CSP Header Example
```
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-uri /csp-report; report-to csp-endpoint

Reporting-Endpoints: csp-endpoint="https://<worker>.workers.dev/csp-report"
```

---

## Anti-patterns
- **No deduplication** — browsers can fire hundreds of reports per page load for the same violation; without upsert your table explodes.
- **Storing `original-policy` on every row** — it can be kilobytes long; consider truncating or hashing if storage is a concern.
- **Blocking the response on Slack posting** — use `ctx.waitUntil` for the Cron digest; never block ingestion on downstream calls.
- **Trusting `document-uri` for security decisions** — CSP reports are unauthenticated; treat all fields as untrusted user input.

---

## Gotchas
- Chrome sends `application/csp-report`; Firefox may send `application/json` for legacy endpoints; the Reporting API uses `application/reports+json` — handle all three content types.
- `blocked-uri` is truncated to the origin for cross-origin resources by some browsers to avoid leaking third-party URLs.
- D1 `ON CONFLICT DO UPDATE` (upsert) requires a `UNIQUE` index on the conflict columns — the schema above includes it.
- The `ScheduledEvent` type must be imported from the `@cloudflare/workers-types` package or declared globally.

---

## Verification
```bash
# Apply schema
wrangler d1 execute my-db --file schema.sql

# Send a test legacy CSP report
curl -X POST https://<worker>.workers.dev/csp-report \
  -H 'Content-Type: application/csp-report' \
  -d '{"csp-report":{"document-uri":"https://example.com","blocked-uri":"https://evil.com/x.js","violated-directive":"script-src","disposition":"report"}}'
# Expect 204

# Send a test Reporting API payload
curl -X POST https://<worker>.workers.dev/csp-report \
  -H 'Content-Type: application/reports+json' \
  -d '[{"type":"csp-violation","url":"https://example.com","body":{"blockedURL":"https://cdn.evil.com/t.js","violatedDirective":"script-src","effectiveDirective":"script-src","originalPolicy":"default-src 'self'","disposition":"report"}}]'

# Query violations
wrangler d1 execute my-db \
  --command "SELECT violated_directive, blocked_uri, count FROM csp_violations ORDER BY count DESC"

# Trigger Cron locally
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+9+*+*+*"
```

---

## Related
- `workers-encrypted-kv-store-aes-gcm.md`
- `workers-bot-detection-cf-turnstile.md`

---

## Sources
- MDN CSP report-uri — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/report-uri
- W3C Reporting API — https://www.w3.org/TR/reporting/
- Cloudflare D1 Batch — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
