# CSP Violation Report Endpoint in Workers with D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You set a Content Security Policy on your site and want to collect `report-uri` (or `report-to`) violation events in a queryable store. Browser-native reporting sends `POST` requests with `application/csp-report` JSON bodies; you need a Worker that validates the origin, inserts the violation into D1, aggregates by directive and day, and fires a Slack alert via a Queue when a directive exceeds a daily threshold. This pattern gives you a fully self-hosted CSP analytics pipeline with no third-party dependency.

---

## Context
Content Security Policy violations are delivered by the browser as `POST` requests to the URL specified in the `report-uri` or `report-to` directive. Each body contains a `csp-report` object with `violated-directive`, `blocked-uri`, `source-file`, `line-number`, and `document-uri`. Storing every event in D1 enables SQL aggregations (top directives, top blocked URIs) without exporting logs. A Cloudflare Queue decouples the Slack notification from the critical path so a slow downstream webhook never delays the 200 OK that the browser expects.

---

## Section 1 — D1 Schema & Wrangler Config

```toml
# wrangler.toml
name = "csp-report-worker"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[[d1_databases]]
binding  = "DB"
database_name = "csp_reports"
database_id   = "<your-d1-id>"

[[queues.producers]]
binding  = "ALERT_QUEUE"
queue    = "csp-alerts"

[[queues.consumers]]
queue    = "csp-alerts"
max_batch_size    = 10
max_batch_timeout = 30

[vars]
ALLOWED_DOCUMENT_ORIGINS = "https://app.example.com,https://www.example.com"
VIOLATION_THRESHOLD      = "50"   # alerts above this per-directive per-day
```

```sql
-- migrations/0001_csp_reports.sql
CREATE TABLE csp_violations (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                INTEGER NOT NULL,              -- Unix epoch ms
  document_uri      TEXT NOT NULL,
  violated_directive TEXT NOT NULL,
  blocked_uri       TEXT,
  source_file       TEXT,
  line_number       INTEGER,
  column_number     INTEGER,
  referrer          TEXT
);

CREATE INDEX idx_csp_ts            ON csp_violations(ts);
CREATE INDEX idx_csp_directive_ts  ON csp_violations(violated_directive, ts);
CREATE INDEX idx_csp_blocked_uri   ON csp_violations(blocked_uri);

-- Aggregation view: violations per directive per calendar day (UTC)
CREATE VIEW csp_daily_summary AS
  SELECT
    date(ts / 1000, 'unixepoch') AS day,
    violated_directive,
    COUNT(*) AS violation_count
  FROM csp_violations
  GROUP BY day, violated_directive;
```

```bash
# Apply migration
npx wrangler d1 execute csp_reports --file=migrations/0001_csp_reports.sql
```

---

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  ALERT_QUEUE: Queue;
  ALLOWED_DOCUMENT_ORIGINS: string;
  VIOLATION_THRESHOLD: string;
}

// CSP report body shape (W3C spec)
interface CspReport {
  "document-uri": string;
  "violated-directive": string;
  "blocked-uri"?: string;
  "source-file"?: string;
  "line-number"?: number;
  "column-number"?: number;
  referrer?: string;
}

interface CspReportBody {
  "csp-report": CspReport;
}

function isAllowedOrigin(documentUri: string, allowedOrigins: string[]): boolean {
  try {
    const parsed = new URL(documentUri);
    return allowedOrigins.some(
      (o) => parsed.origin === new URL(o.trim()).origin
    );
  } catch {
    return false;
  }
}

async function insertViolation(
  report: CspReport,
  ts: number,
  db: D1Database
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO csp_violations
         (ts, document_uri, violated_directive, blocked_uri,
          source_file, line_number, column_number, referrer)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(
      ts,
      report["document-uri"],
      report["violated-directive"],
      report["blocked-uri"] ?? null,
      report["source-file"] ?? null,
      report["line-number"] ?? null,
      report["column-number"] ?? null,
      report["referrer"] ?? null
    )
    .run();
}

async function checkThresholdAndAlert(
  directive: string,
  threshold: number,
  db: D1Database,
  queue: Queue
): Promise<void> {
  const dayStart = new Date();
  dayStart.setUTCHours(0, 0, 0, 0);
  const dayStartMs = dayStart.getTime();

  const row = await db
    .prepare(
      `SELECT COUNT(*) as n FROM csp_violations
       WHERE violated_directive = ? AND ts >= ?`
    )
    .bind(directive, dayStartMs)
    .first<{ n: number }>();

  if (!row) return;
  if (row.n >= threshold && row.n % threshold === 0) {
    // Alert every time we hit a multiple of the threshold (not on every insert)
    await queue.send({
      type: "csp_threshold_alert",
      directive,
      count: row.n,
      day: dayStart.toISOString().slice(0, 10),
    });
  }
}

export default {
  // ── HTTP handler: receives CSP reports ───────────────────────────────────
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname !== "/csp-report" || request.method !== "POST") {
      return new Response("Not found", { status: 404 });
    }

    const contentType = request.headers.get("content-type") ?? "";
    if (
      !contentType.includes("application/csp-report") &&
      !contentType.includes("application/json")
    ) {
      return new Response("Unsupported Media Type", { status: 415 });
    }

    let body: CspReportBody;
    try {
      body = await request.json<CspReportBody>();
    } catch {
      return new Response("Invalid JSON", { status: 400 });
    }

    const report = body["csp-report"];
    if (!report || !report["document-uri"] || !report["violated-directive"]) {
      return new Response("Missing required fields", { status: 400 });
    }

    // Validate document origin
    const allowedOrigins = env.ALLOWED_DOCUMENT_ORIGINS.split(",");
    if (!isAllowedOrigin(report["document-uri"], allowedOrigins)) {
      return new Response("Forbidden", { status: 403 });
    }

    const ts = Date.now();
    const threshold = parseInt(env.VIOLATION_THRESHOLD, 10);

    // Insert then check threshold (non-blocking alert via Queue)
    await insertViolation(report, ts, env.DB);
    await checkThresholdAndAlert(
      report["violated-directive"],
      threshold,
      env.DB,
      env.ALERT_QUEUE
    );

    // CSP report endpoints must return 2xx; body is ignored by the browser
    return new Response(null, { status: 204 });
  },

  // ── Queue consumer: sends Slack notifications ────────────────────────────
  async queue(batch: MessageBatch<unknown>, env: Env): Promise<void> {
    const slackWebhook = (env as unknown as { SLACK_WEBHOOK_URL: string })
      .SLACK_WEBHOOK_URL;
    if (!slackWebhook) return;

    for (const msg of batch.messages) {
      const data = msg.body as {
        type: string;
        directive: string;
        count: number;
        day: string;
      };

      if (data.type !== "csp_threshold_alert") {
        msg.ack();
        continue;
      }

      const text =
        `:shield: *CSP Alert* — \`${data.directive}\` reached *${data.count}* violations on ${data.day}`;

      const res = await fetch(slackWebhook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (res.ok) {
        msg.ack();
      } else {
        msg.retry();
      }
    }
  },
};
```

---

## Section 3 — Integration / Testing

```typescript
// test/csp-report.test.ts
import { unstable_dev } from "wrangler";
import { describe, it, expect, beforeAll, afterAll } from "vitest";

describe("CSP report endpoint", () => {
  let worker: Awaited<ReturnType<typeof unstable_dev>>;

  const validReport = {
    "csp-report": {
      "document-uri": "https://app.example.com/page",
      "violated-directive": "script-src",
      "blocked-uri": "https://evil.com/x.js",
      "source-file": "https://app.example.com/page",
      "line-number": 42,
    },
  };

  beforeAll(async () => {
    worker = await unstable_dev("src/index.ts", {
      experimental: { disableExperimentalWarning: true },
      vars: {
        ALLOWED_DOCUMENT_ORIGINS: "https://app.example.com",
        VIOLATION_THRESHOLD: "50",
      },
    });
  });

  afterAll(async () => { await worker.stop(); });

  it("returns 204 for valid report", async () => {
    const res = await worker.fetch("/csp-report", {
      method: "POST",
      headers: { "Content-Type": "application/csp-report" },
      body: JSON.stringify(validReport),
    });
    expect(res.status).toBe(204);
  });

  it("returns 403 for disallowed origin", async () => {
    const report = {
      "csp-report": {
        ...validReport["csp-report"],
        "document-uri": "https://attacker.com/page",
      },
    };
    const res = await worker.fetch("/csp-report", {
      method: "POST",
      headers: { "Content-Type": "application/csp-report" },
      body: JSON.stringify(report),
    });
    expect(res.status).toBe(403);
  });

  it("returns 415 for wrong content-type", async () => {
    const res = await worker.fetch("/csp-report", {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: JSON.stringify(validReport),
    });
    expect(res.status).toBe(415);
  });
});
```

```bash
# Send a test CSP report manually
curl -X POST https://csp-report-worker.example.workers.dev/csp-report \
  -H "Content-Type: application/csp-report" \
  -d '{ "csp-report": { "document-uri": "https://app.example.com/", "violated-directive": "script-src", "blocked-uri": "https://evil.com/x.js" } }'

# Top violations today
npx wrangler d1 execute csp_reports \
  --command="SELECT violated_directive, COUNT(*) as n FROM csp_violations WHERE ts >= $(date -d 'today 00:00:00 UTC' +%s)000 GROUP BY violated_directive ORDER BY n DESC LIMIT 10"

# Daily summary from view
npx wrangler d1 execute csp_reports \
  --command="SELECT * FROM csp_daily_summary ORDER BY day DESC, violation_count DESC LIMIT 20"
```

---

## Anti-patterns
- **No origin validation** — An open CSP report endpoint can be spammed by any external site; always verify `document-uri` maps to an origin you own.
- **Synchronous Slack HTTP call in the fetch handler** — A slow or unavailable Slack webhook delays the 204 response; the browser may time out and retry, causing duplicate inserts. Use a Queue for all outbound webhooks.
- **Inserting without TTL / cleanup job** — CSP violation tables can grow to millions of rows; add a daily `DELETE FROM csp_violations WHERE ts < epoch_30_days_ago` cron via Cron Triggers.
- **Alerting on every violation** — Firing Slack for each row causes alert fatigue; gate alerts on crossing a daily threshold, as shown above.

---

## Gotchas
- Browsers send `application/csp-report` (not `application/json`); always accept both content types to handle older and newer browser implementations.
- Some browsers omit `blocked-uri` for inline violations, sending an empty string instead of `null`; normalize empty strings to `null` before inserting.
- The `report-to` header (Reporting API v1) sends a different body format: `[{"type":"csp-violation","body":{...}}]`; extend the parser if you need to support both.
- D1 `COUNT(*)` scans the full index range; for very high-volume sites (millions of rows/day) consider a pre-aggregated counter in KV incremented atomically via Durable Objects.
- The Queue consumer runs in a separate invocation; it does not share the same `env` object as the fetch handler. Store `SLACK_WEBHOOK_URL` as a secret on the same Worker.

---

## Verification
```bash
# Deploy
npx wrangler deploy

# Set Slack webhook secret
npx wrangler secret put SLACK_WEBHOOK_URL

# Confirm D1 rows after sending reports
npx wrangler d1 execute csp_reports \
  --command="SELECT * FROM csp_violations ORDER BY id DESC LIMIT 5"

# Check queue backlog (should be 0 if Slack is reachable)
npx wrangler queues consumer list csp-alerts
```

---

## Related
- `workers-sri-hash-html-rewriter.md`
- `workers-oauth2-pkce-authorization-code.md`

---

## Sources
- W3C Content Security Policy Level 3 — https://www.w3.org/TR/CSP3/
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Cloudflare Queues docs — https://developers.cloudflare.com/queues/
- Reporting API (W3C) — https://www.w3.org/TR/reporting/
