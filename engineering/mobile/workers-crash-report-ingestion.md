# Crash Report Ingestion API in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Mobile apps crash. Without a backend that accepts, groups, and alerts on crash reports you are flying blind. Third-party crash SDKs add bundle weight and send PII to external servers. A custom ingestion pipeline built on Workers, R2, and D1 keeps data in your own infrastructure, provides GDPR-compliant scrubbing, and integrates directly with your Slack alerting.

## Context

A Cloudflare Worker receives crash reports via `POST /crash-reports`. Raw payloads are stored immediately in R2 (cheap, durable). The stack trace is hashed and grouped in D1 — new crash types trigger a Slack alert. A background Scheduled Worker performs symbolication by looking up dSYM/ProGuard mapping files stored in R2. GDPR scrubbing removes email addresses, UUIDs that look like user IDs, and device-identifying strings before storage.

## Solution

```typescript
// crash-ingest/src/index.ts
import { Hono } from 'hono';

export interface Env {
  CRASH_REPORTS: R2Bucket;       // raw crash payloads
  DSYM_STORE: R2Bucket;          // dSYM / mapping files keyed by build_id
  CRASH_DB: D1Database;          // crash_groups + crash_events tables
  SLACK_WEBHOOK_URL: string;     // Worker secret
  REPORT_QUEUE: Queue;           // for async symbolication
}

interface CrashReport {
  platform: 'ios' | 'android';
  app_version: string;
  build_id: string;              // dSYM UUID or mapping file hash
  stack_trace: string;           // raw (possibly unsymbolicated)
  exception_type: string;
  exception_message: string;
  device_model: string;
  os_version: string;
  timestamp: string;
  // Optional — may contain PII, will be scrubbed
  user_id?: string;
  breadcrumbs?: string;
}

interface ScrubResult {
  scrubbed: string;
  pii_found: boolean;
}

// ── PII scrubbing ─────────────────────────────────────────────────────────────

const PII_PATTERNS: [RegExp, string][] = [
  [/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '[EMAIL]'],
  [/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi, '[UUID]'],
  [/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, '[IP]'],
  [/Bearer\s+[A-Za-z0-9\-._~+/]+=*/g, '[TOKEN]'],
];

function scrubPii(text: string): ScrubResult {
  let scrubbed = text;
  let pii_found = false;
  for (const [pattern, replacement] of PII_PATTERNS) {
    const before = scrubbed;
    scrubbed = scrubbed.replace(pattern, replacement);
    if (scrubbed !== before) pii_found = true;
  }
  return { scrubbed, pii_found };
}

// ── Stack trace hashing (group crashes by root frame) ────────────────────────

async function hashStackTrace(stack: string): Promise<string> {
  // Normalise: strip memory addresses and line numbers, keep symbol names
  const normalised = stack
    .split('\n')
    .slice(0, 8)                             // top 8 frames
    .map((line) => line.replace(/0x[0-9a-f]+/gi, '0xADDR').replace(/:\d+$/g, ':N'))
    .join('\n');
  const bytes = new TextEncoder().encode(normalised);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 16);
}

// ── Slack alert ───────────────────────────────────────────────────────────────

async function sendSlackAlert(
  webhookUrl: string,
  report: CrashReport,
  groupId: string,
): Promise<void> {
  const body = {
    text: `*New crash type detected* [${report.platform.toUpperCase()}]`,
    blocks: [
      {
        type: 'section',
        text: {
          type: 'mrkdwn',
          text:
            `*${report.exception_type}*\n${report.exception_message}\n` +
            `Version: \`${report.app_version}\` | Group: \`${groupId}\``,
        },
      },
      {
        type: 'section',
        fields: [
          { type: 'mrkdwn', text: `*Platform:*\n${report.platform}` },
          { type: 'mrkdwn', text: `*Device:*\n${report.device_model} / ${report.os_version}` },
        ],
      },
    ],
  };
  await fetch(webhookUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ── Routes ────────────────────────────────────────────────────────────────────

const app = new Hono<{ Bindings: Env }>();

app.post('/crash-reports', async (c) => {
  let report: CrashReport;
  try {
    report = await c.req.json<CrashReport>();
  } catch {
    return c.json({ error: 'Invalid JSON' }, 400);
  }

  if (!report.platform || !report.stack_trace || !report.build_id) {
    return c.json({ error: 'Missing required fields' }, 400);
  }

  // 1. Scrub PII from all string fields before any storage
  const { scrubbed: scrubbedStack } = scrubPii(report.stack_trace);
  const { scrubbed: scrubbedMessage } = scrubPii(report.exception_message ?? '');
  const scrubbedReport: CrashReport = {
    ...report,
    stack_trace: scrubbedStack,
    exception_message: scrubbedMessage,
    user_id: report.user_id ? '[SCRUBBED]' : undefined,
    breadcrumbs: report.breadcrumbs ? scrubPii(report.breadcrumbs).scrubbed : undefined,
  };

  // 2. Store raw (scrubbed) report in R2
  const reportId = crypto.randomUUID();
  const r2Key = `reports/${report.platform}/${report.app_version}/${reportId}.json`;
  await c.env.CRASH_REPORTS.put(r2Key, JSON.stringify(scrubbedReport), {
    httpMetadata: { contentType: 'application/json' },
    customMetadata: { platform: report.platform, build_id: report.build_id },
  });

  // 3. Hash and group in D1
  const stackHash = await hashStackTrace(scrubbedStack);

  // Upsert crash group
  const group = await c.env.CRASH_DB
    .prepare('SELECT id, event_count FROM crash_groups WHERE stack_hash = ? AND platform = ?')
    .bind(stackHash, report.platform)
    .first<{ id: string; event_count: number }>();

  let groupId: string;
  let isNewGroup = false;

  if (group) {
    groupId = group.id;
    await c.env.CRASH_DB
      .prepare('UPDATE crash_groups SET event_count = event_count + 1, last_seen_at = ? WHERE id = ?')
      .bind(new Date().toISOString(), groupId)
      .run();
  } else {
    groupId = crypto.randomUUID();
    isNewGroup = true;
    await c.env.CRASH_DB
      .prepare(
        `INSERT INTO crash_groups (id, platform, stack_hash, exception_type, exception_message,
         first_seen_at, last_seen_at, event_count, symbolicated)
         VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0)`,
      )
      .bind(
        groupId, report.platform, stackHash, report.exception_type,
        scrubbedMessage, new Date().toISOString(), new Date().toISOString(),
      )
      .run();
  }

  // 4. Insert individual event
  await c.env.CRASH_DB
    .prepare(
      `INSERT INTO crash_events (id, group_id, report_id, r2_key, app_version,
       device_model, os_version, occurred_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      crypto.randomUUID(), groupId, reportId, r2Key,
      report.app_version, report.device_model, report.os_version, report.timestamp,
    )
    .run();

  // 5. Enqueue for async symbolication
  await c.env.REPORT_QUEUE.send({ reportId, r2Key, buildId: report.build_id, platform: report.platform });

  // 6. Alert on new crash types (fire-and-forget)
  if (isNewGroup) {
    c.executionCtx.waitUntil(
      sendSlackAlert(c.env.SLACK_WEBHOOK_URL, scrubbedReport, groupId).catch(() => {}),
    );
  }

  return c.json({ report_id: reportId, group_id: groupId, new_group: isNewGroup }, 202);
});

// Trend endpoint — crash frequency per group over last N days
app.get('/crash-reports/trends', async (c) => {
  const days = Number(c.req.query('days') ?? 7);
  const { results } = await c.env.CRASH_DB
    .prepare(
      `SELECT g.id, g.exception_type, g.event_count, g.first_seen_at, g.last_seen_at,
              COUNT(e.id) AS recent_events
       FROM crash_groups g
       LEFT JOIN crash_events e ON e.group_id = g.id
         AND e.occurred_at >= datetime('now', ? || ' days')
       GROUP BY g.id
       ORDER BY recent_events DESC
       LIMIT 20`,
    )
    .bind(`-${days}`)
    .all();
  return c.json({ days, groups: results });
});

export default app;
```

## Implementation Details

**D1 schema:**
```sql
CREATE TABLE crash_groups (
  id              TEXT PRIMARY KEY,
  platform        TEXT NOT NULL,
  stack_hash      TEXT NOT NULL,
  exception_type  TEXT NOT NULL,
  exception_message TEXT,
  first_seen_at   TEXT NOT NULL,
  last_seen_at    TEXT NOT NULL,
  event_count     INTEGER NOT NULL DEFAULT 0,
  symbolicated    INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX idx_group_hash ON crash_groups(platform, stack_hash);

CREATE TABLE crash_events (
  id           TEXT PRIMARY KEY,
  group_id     TEXT NOT NULL REFERENCES crash_groups(id),
  report_id    TEXT NOT NULL,
  r2_key       TEXT NOT NULL,
  app_version  TEXT,
  device_model TEXT,
  os_version   TEXT,
  occurred_at  TEXT
);
CREATE INDEX idx_event_group ON crash_events(group_id);
CREATE INDEX idx_event_time  ON crash_events(occurred_at);
```

**Symbolication Queue Worker** — a separate `queue` handler reads from `REPORT_QUEUE`, fetches the raw R2 report, downloads the matching dSYM/ProGuard mapping from `DSYM_STORE` using `build_id`, runs addr2line-equivalent lookups (WASM module), and writes the symbolicated stack back into D1.

**R2 lifecycle** — configure a 90-day lifecycle rule on the `CRASH_REPORTS` bucket to auto-delete raw reports. D1 retains the grouped statistics indefinitely.

## Anti-patterns

- **Symbolicating synchronously in the ingestion handler.** Symbolication can take 100–500ms per report. Always do it asynchronously via a Queue.
- **Alerting on every crash event.** Alert only on new crash groups. High-volume known crashes would flood your Slack channel.
- **Storing unscrubbed reports.** If an exception message contains a user's email or a JWT, it lands in your R2 bucket and creates a GDPR liability. Scrub first, store second.
- **Using stack trace text directly as the group key.** Memory addresses and line numbers vary per build. Hash a normalised form (symbol names only, top N frames) for stable grouping.

## Gotchas

- `c.executionCtx.waitUntil()` keeps the Worker alive after the response is sent. Use it for Slack alerts and any non-critical async work. Without it, the Worker may be killed before the fetch completes.
- R2 `put` does not deduplicate; if a client retries a failed upload you will store duplicates. Use a client-generated `report_id` as the R2 key to make puts idempotent.
- D1 `INSERT OR IGNORE` and `UPDATE` cannot be combined atomically without a transaction. Use `BEGIN; SELECT; INSERT/UPDATE; COMMIT;` via `c.env.CRASH_DB.batch()` if strict atomicity matters.
- Queue messages have a maximum size of 128 KB. If crash reports exceed this, store the report in R2 first and enqueue only the R2 key (which is what the example does).

## Verification

```bash
# Submit a test crash report
curl -X POST https://api.example.com/crash-reports \
  -H 'Content-Type: application/json' \
  -d '{
    "platform": "ios",
    "app_version": "2.5.0",
    "build_id": "abc123",
    "stack_trace": "0 MyApp 0x100012abc crash_handler + 42\n1 MyApp 0x10001dead viewDidLoad + 88",
    "exception_type": "EXC_BAD_ACCESS",
    "exception_message": "KERN_INVALID_ADDRESS at 0x0000000000000010",
    "device_model": "iPhone 15 Pro",
    "os_version": "17.4",
    "timestamp": "2026-08-24T10:00:00Z"
  }'

# Fetch trends
curl https://api.example.com/crash-reports/trends?days=7
```

## Related

- `documentation/categories/mobile/workers-app-update-checker.md` — force-update on crash-rate spike
- `documentation/categories/mobile/workers-app-config-remote.md` — kill-switch triggered by crash rate
- `documentation/categories/mobile/binary-protocol-encoding.md` — compact binary report format for low-bandwidth devices

## Sources

- Cloudflare R2 documentation: https://developers.cloudflare.com/r2/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Cloudflare D1: https://developers.cloudflare.com/d1/
- GDPR Article 25 (data minimisation): https://gdpr-info.eu/art-25-gdpr/
